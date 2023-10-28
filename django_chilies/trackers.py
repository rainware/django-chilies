import datetime
import json
import logging
import os
import socket
import sys
import threading
import traceback
from copy import deepcopy

from . import writers
from .settings import get_trackers_config, get_default_level, get_default_buffer_size, get_default_console, get_base_dir
from .utils import JSONEncoder, generate_uuid, get_func

sys_logger = logging.getLogger('django.server')

trackers_config = get_trackers_config()
default_buffer_size = get_default_buffer_size()
default_level = get_default_level()
default_console = get_default_console()
base_dir = get_base_dir()


def get_level_name(level):
    if level == logging.WARN:
        return 'WARN'
    else:
        return logging.getLevelName(level)


def instance_from_settings(name, trace_id=None):
    assert name in trackers_config, 'tracker config not exist: %s' % name
    config = trackers_config[name]
    cls = get_func(config['class'])

    _writers = []
    for writer_name in config.get('writers'):
        _writers.append(writers.instance_from_settings(writer_name))

    return cls(name=name,
               trace_id=trace_id,
               level=logging.getLevelName(config.get('level', default_level)),
               buffer_size=config.get('buffer_size', default_buffer_size),
               console=logging.getLogger(config.get('console', default_console)),
               writers=_writers
               )


class Logger(object):
    """
    logger
    """

    def __init__(self,
                 name='',
                 level=logging.NOTSET,
                 buffer_size=1,
                 console=logging
                 ):
        self.console = console
        # self.console.level = level
        self.name = name
        self._buf = []
        self.level = level
        self.buffer_size = buffer_size
        self.ignore_empty_lines = True

    @property
    def length(self):
        return len(self._buf)

    @property
    def is_empty(self):
        return self.length == 0

    def debug(self, message):
        if self.level <= logging.DEBUG:
            self.write(self._format(message, 'DEBUG'))
            self.console.debug(message)
            return True
        return False

    def info(self, message):
        if self.level <= logging.INFO:
            self.write(self._format(message, 'INFO'))
            self.console.info(message)
            return True
        return False

    def warn(self, message):
        if self.level <= logging.WARNING:
            self.write(self._format(message, 'WARN'))
            self.console.warning(message)
            return True
        return False

    def error(self, message):
        if self.level <= logging.ERROR:
            self.write(self._format(message, 'ERROR'))
            self.console.error(message)
            return True
        return False

    def flush(self):
        message = '\n'.join(self._buf)
        self._buf.clear()
        return message

    def write(self, content):
        if self.length < self.buffer_size:
            self._buf.append(content)
        else:
            # TODO:
            pass

    def _format(self, content, level):
        content = str(content).strip('\n')
        co_filename, func_lineno, co_name = self._find_caller()
        return '[%s] %s %s:%s: [line:%s] %s' % (
            datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4],
            level,
            # os.path.relpath(co_filename, base_dir),
            # co_filename.replace(base_dir, ''),
            co_filename,
            co_name,
            func_lineno,
            content
        )

    def exception(self, e=None, with_stack=True):
        if self.level <= logging.ERROR:
            if isinstance(e, Exception):
                e_type, e_value, traceback_obj = type(e), e, e.__traceback__
            else:
                e_type, e_value, traceback_obj = sys.exc_info()[:3]
                if e:
                    self.error(e)

            self.console.exception(e_value)
            title = '%s:%s' % (e_type, e_value)
            self.error(title)

            lines = [title]
            if with_stack:
                # lines.append('ErrorStack:')
                # self.write('ErrorStack:')
                for line in traceback.format_exception(e_type, e_value, traceback_obj)[1:]:
                    line = line.rstrip('\n')
                    lines.append(line)
                    self.write(line)
            return True

        return False

    def _find_caller(self):
        """
        获取调用者信息, 用于记录file func lineno
        :return:
        """

        f = logging.currentframe()

        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)"
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename == __file__:
                f = f.f_back
                continue
            rv = (co.co_filename, f.f_lineno, co.co_name)
            break
        return rv


class SessionLogger(Logger):

    def __init__(self, tracker, *args, **kwargs):
        self.create_time = datetime.datetime.now(datetime.timezone.utc)
        self.tracker = tracker
        self.with_context = kwargs.pop('with_context', False)
        self.catch_exc = kwargs.pop('catch_exc', True)
        self.args = deepcopy(args)
        self.kwargs = deepcopy(kwargs)
        self.session_level = logging.DEBUG
        self.error_payload = None
        self.has_error = False
        self.has_warning = False
        super().__init__(tracker.name, *args, **kwargs)

    def clone(self, with_context=False, catch_exc=False):
        s = self.__class__(self.tracker, with_context=with_context, catch_exc=catch_exc, *self.args, **self.kwargs)
        return s

    def persistent(self):
        if not self.is_empty:
            self.tracker.persistent(self)

    def close(self):
        self.persistent()

    def set_session_level(self, level):
        self.session_level = level

    def set_error(self, e=None, with_stack=True):
        self.set_session_level(logging.ERROR)
        self.has_error = True
        if e:
            e_type, e_value, traceback_obj = type(e), e, e.__traceback__
        else:
            e_type, e_value, traceback_obj = sys.exc_info()[:3]
        stack = None
        if with_stack:
            lines = []
            for line in traceback.format_exception(e_type, e_value, traceback_obj):
                line = line.rstrip('\n')
                lines.append(line)
            stack = '\n'.join(lines)
        self.error_payload = {
            'type': e_type.__name__ if e_type else '',
            'value': str(e_value),
            'stack': stack
        }
        self.console.exception(e_value)

    def debug(self, *args, **kwargs):
        return super().debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        res = super().info(*args, **kwargs)
        if res:
            if self.session_level < logging.INFO:
                self.set_session_level(logging.INFO)
        return res

    def warn(self, *args, **kwargs):
        res = super().warn(*args, **kwargs)
        if res:
            self.has_warning = True
            if self.session_level < logging.WARN:
                self.set_session_level(logging.WARN)
        return res

    def warning(self, *args, **kwargs):
        return self.warn(*args, **kwargs)

    def error(self, *args, **kwargs):
        res = super().error(*args, **kwargs)
        if res:
            # session的has_error代表本次session的结果，由set_error函数来设置
            # 手动error/exception记录的错误，被视为warning
            self.has_warning = True
            if self.session_level < logging.ERROR:
                self.set_session_level(logging.WARN)
        return res

    def exception(self, *args, **kwargs):
        res = super().exception(*args, **kwargs)
        if res:
            # session的has_error代表本次session的结果，由set_error函数来设置
            # 手动error/exception记录的错误，被视为warning
            self.has_warning = True
            if self.session_level < logging.ERROR:
                self.set_session_level(logging.WARN)
        return res

    def __enter__(self, ):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.set_error()
        self.close()
        return not exc_val or self.catch_exc


class Tracker(object):

    def __init__(self, name, *args, **kwargs):
        # super().__init__(*args, **kwargs)
        self.create_time = datetime.datetime.now(datetime.timezone.utc)
        self.name = name
        self.writers = kwargs.pop('writers', [])
        self.trace_id = kwargs.pop('trace_id', generate_uuid())
        self.session = SessionLogger(self, with_context=True, *args, **kwargs)
        self.console = self.session.console
        self.context = {
            'level': logging.INFO,
            'has_error': False,
            'has_warning': False,
            'error': None,
            'attrs': {}
        }

    def set_attr(self, k, v):
        self.context['attrs'][k] = v

    def get_attr(self, k):
        return self.context['attrs'][k]

    def new_session(self, with_context=False, catch_exc=False):
        return self.session.clone(with_context=with_context, catch_exc=catch_exc)

    def debug(self, *args, **kwargs):
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.debug(*args, **kwargs)
        return self.session.debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.info(*args, **kwargs)
        return self.session.info(*args, **kwargs)

    def warn(self, *args, **kwargs):
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.warn(*args, **kwargs)
        res = self.session.warn(*args, **kwargs)
        if res:
            self.context['has_warning'] = True
            if self.context['level'] < logging.WARN:
                self.set_context_level(logging.WARN)
        return res

    def warning(self, *args, **kwargs):
        return self.warn(*args, **kwargs)

    def error(self, *args, **kwargs):
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.error(*args, **kwargs)
        res = self.session.error(*args, **kwargs)
        if res:
            # tracker的has_error代表本次track的结果，由set_error函数来设置
            # 手动error/exception记录的错误，被视为warning
            self.context['has_warning'] = True
            if self.context['level'] < logging.ERROR:
                self.set_context_level(logging.WARN)
        return res

    def exception(self, *args, **kwargs):
        kwargs['with_stack'] = kwargs.get('with_stack', True)
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.exception(*args, **kwargs)
        res = self.session.exception(*args, **kwargs)
        if res:
            # tracker的has_error代表本次track的结果，由set_error函数来设置
            # 手动error/exception记录的错误，被视为warning
            self.context['has_warning'] = True
            if self.context['level'] < logging.ERROR:
                self.set_context_level(logging.WARN)

        return res

    def persistent(self, session=None):
        session = session or self.session
        try:
            message = self.get_message(session)
            message = self.filter_message(message)
            for writer in self.writers:
                try:
                    writer.write(message)
                    writer.flush()
                except Exception as e:
                    sys_logger.exception(e)
        except Exception as e:
            sys_logger.exception(e)

    def set_trace_id(self, _id):
        self.trace_id = _id

    def get_message(self, session):
        raise NotImplementedError()

    def filter_message(self, o):
        """
        to be override
        :param o:
        :return:
        """
        return o

    def set_context_level(self, level):
        self.context['level'] = level

    def set_error(self, e=None, with_stack=True):
        self.set_context_level(logging.ERROR)
        self.context['has_error'] = True
        if e:
            e_type, e_value, traceback_obj = type(e), e, e.__traceback__
        else:
            e_type, e_value, traceback_obj = sys.exc_info()[:3]
        stack = None
        if with_stack:
            lines = []
            for line in traceback.format_exception(e_type, e_value, traceback_obj):
                line = line.rstrip('\n')
                lines.append(line)
            stack = '\n'.join(lines)
        self.context['error'] = {
            'type': e_type.__name__ if e_type else '',
            'value': str(e_value),
            'stack': stack
        }
        self.console.exception(e_value)


class HTTPTracker(Tracker):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context.update(dict(http={
            'status_code': None,
            'method': None,
            'url': None,
            'url_name': None,
            'url_namespace': None,
            'query_string': None,
            'duration': None
        }, request={
            'id': None,
            'header': None,
            'Header': None,
            'Body': None,
            'params': None,
            'Params': None,
        }, response={
            'header': None,
            'Header': None,
            'data': None,
            'Data': None,
            'Body': None
        }, api={
            'code': None,
            'message': None,
        }, user={}, operator={}))

        self.request_params_tracked = False

    def set_request_id(self, _id):
        self.context['request']['id'] = _id
        self.console.debug('Request ID: %s', _id)

    def set_http_info(self, info):
        self.context['http']['method'] = info.get('method')
        self.context['http']['url'] = info.get('url')
        self.context['http']['url_name'] = info.get('url_name')
        self.context['http']['url_namespace'] = info.get('url_namespace')
        self.context['http']['query_string'] = info.get('query_string')
        text = '%s %s received' % (
            self.context['http']['method'],
            self.context['http']['url'] if not self.context['http']['query_string'] else '%s?%s' % (
                self.context['http']['url'], self.context['http']['query_string'])
        )
        self.console.info(text)

    def set_request_headers(self, headers, formats=['json', 'text']):
        text = json.dumps(headers, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['request']['header'] = headers
        if 'text' in formats:
            self.context['request']['Header'] = text
        self.console.debug('RequestHeader: %s', text)

    def set_request_body(self, body):
        self.context['request']['Body'] = body
        self.console.debug('RequestBody: %s', body)

    def set_request_params(self, params, formats=['json', 'text']):
        text = json.dumps(params, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['request']['params'] = params
        if 'text' in formats:
            self.context['request']['Params'] = text
        self.console.debug('RequestParams: %s', text)
        self.request_params_tracked = True

    def set_response_headers(self, headers, formats=['json', 'text']):
        text = json.dumps(headers, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['response']['header'] = headers
        if 'text' in formats:
            self.context['response']['Header'] = text
        self.console.debug('ResponseHeader: %s', text)

    def set_response_data(self, data, formats=['json', 'text']):
        self.context['api']['code'] = data.get('code')
        self.context['api']['message'] = data.get('message')
        if str(data['code']).startswith('5'):
            self.set_context_level(logging.ERROR)
        elif str(data['code']).startswith('4'):
            self.set_context_level(logging.WARN)
        else:
            self.set_context_level(logging.INFO)

        text = json.dumps(data, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['response']['data'] = data
        if 'text' in formats:
            self.context['response']['Data'] = text
        self.console.debug('ResponseData: %s', text)

    def set_response_body(self, body):
        self.context['response']['Body'] = body
        self.console.debug('ResponseBody: %s', body)

    def set_http_result(self, info):
        self.context['http']['duration'] = info.get('duration')
        self.context['http']['status_code'] = info.get('status_code')
        text = '%s %s %.1fms %s %s %s' % (
            self.context['http']['method'],
            self.context['http']['url'] if not self.context['http']['query_string'] else '%s?%s' % (
                self.context['http']['url'], self.context['http']['query_string']),
            self.context['http']['duration'],
            self.context['http']['status_code'],
            self.context['api']['code'],
            self.context['api']['message'])

        if self.context['has_error']:
            self.session.error(text)
        elif self.context['has_warning']:
            self.session.warn(text)
        else:
            self.session.info(text)

    def set_user(self, user):
        if user:
            self.context['user'] = user
        text = json.dumps(self.context['user'], ensure_ascii=False, cls=JSONEncoder)
        self.console.debug('User: %s' % text)

    def set_operator(self, operator):
        if operator:
            self.context['operator'] = operator
        text = json.dumps(self.context['operator'], ensure_ascii=False, cls=JSONEncoder)
        self.console.debug('Operator: %s' % text)

    def get_message(self, session):
        msg = {
            "@version": "1",
            'type': 'HTTPTracker',
            "logger_name": self.name,
            "trace_id": self.trace_id,
            "thread_name": threading.current_thread().getName(),
            # "app": settings.APP_NAME,
            # "env_name": os.getenv('ENV_NAME', ''),
            "hostname": socket.gethostname(),
            "host_ip": socket.gethostbyname(socket.gethostname()),
            "with_context": session.with_context,
            "message": session.flush(),
            "status_code": self.context['http']['status_code']
        }
        if session.with_context:
            msg['@timestamp'] = self.create_time.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
            msg = {**msg, **self.context}
        else:
            msg['@timestamp'] = session.create_time.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
            msg['level'] = session.session_level
            msg['has_error'] = session.has_error
            msg['has_warning'] = session.has_warning
            msg['http'] = self.context['http']
        msg['level'] = get_level_name(msg['level'])
        if not msg.get('error') and session.error_payload:
            msg['error'] = session.error_payload
        return msg


class TaskTracker(Tracker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context.update(dict(task={
            'name': None,
            'module': None,
            'filename': None,
        }, execution={
            'id': None,
            'header': None,
            'Header': None,
            'params': None,
            'Params': None,
            'data': None,
            'Data': None,
            'duration': None
        }))

    def set_task_info(self, info):
        self.context['execution']['id'] = info['id']
        self.context['task']['name'] = info['name']
        self.context['task']['module'] = info['module']
        self.context['task']['filename'] = info['filename']

        text = 'task %s.%s received' % (
            self.context['task']['module'],
            self.context['task']['name'],
        )
        self.console.info(text)
        self.console.debug('Execution ID: %s' % self.context['execution']['id'])

    def set_task_headers(self, headers, formats=['json', 'text']):
        text = json.dumps(headers, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['execution']['header'] = headers
        if 'text' in formats:
            self.context['execution']['Header'] = text
        self.console.debug('TaskHeaders: %s', text)

    def set_task_params(self, params, formats=['json', 'text']):
        text = json.dumps(params, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['execution']['params'] = params
        if 'text' in formats:
            self.context['execution']['Params'] = text
        self.console.debug('TaskParams: %s' % text)

    def set_task_data(self, data, formats=['json', 'text']):
        text = json.dumps(data, ensure_ascii=False, cls=JSONEncoder)
        if 'json' in formats:
            self.context['execution']['data'] = data
        if 'text' in formats:
            self.context['execution']['Data'] = text
        self.console.debug('TaskData: %s' % text)

    def set_task_result(self, info):
        self.context['execution']['duration'] = info['duration']
        text = 'task %s.%s %.1fms' % (
            self.context['task']['module'],
            self.context['task']['name'],
            self.context['execution']['duration']
            # self.context['TaskParams'],
            # self.context['TaskData']
        )
        if self.context['has_error']:
            self.session.error(text)
        elif self.context['has_warning']:
            self.session.warn(text)
        else:
            self.session.info(text)

    def get_message(self, session):
        msg = {
            "@version": "1",
            "type": 'TaskTracker',
            "logger_name": self.name,
            "trace_id": self.trace_id,
            "thread_name": threading.current_thread().getName(),
            # "level_value": None,
            # "app": settings.APP_NAME,
            # "env_name": os.getenv('ENV_NAME', ''),
            "hostname": socket.gethostname(),
            "host_ip": socket.gethostbyname(socket.gethostname()),
            "with_context": session.with_context,
            "message": session.flush()
        }
        if session.with_context:
            msg['@timestamp'] = self.create_time.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
            msg = {**msg, **self.context}
        else:
            msg['@timestamp'] = session.create_time.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
            msg['level'] = session.session_level
            msg['has_error'] = session.has_error
            msg['has_warning'] = session.has_warning
            msg['task'] = self.context['task']
        msg['level'] = get_level_name(msg['level'])
        if not msg.get('error') and session.error_payload:
            msg['error'] = session.error_payload
        return msg
