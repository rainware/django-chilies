import datetime
import json
import logging
import os
import socket
import sys
import threading
import traceback
from copy import deepcopy

from django.conf import settings

from . import writers
from .settings import TRACKER_DEFAULT
from .utils import CustomJsonEncoder, generate_uuid, get_func

sys_logger = logging.getLogger('django')

trackers_config = dict(TRACKER_DEFAULT['trackers'], **settings.DJANGO_CHILIES_TRACKER.get('trackers', {}))
default_buffer_size = settings.DJANGO_CHILIES_TRACKER.get('buffer_size') or TRACKER_DEFAULT['buffer_size']
default_level = settings.DJANGO_CHILIES_TRACKER.get('level') or TRACKER_DEFAULT['level']
default_console = settings.DJANGO_CHILIES_TRACKER.get('console') or TRACKER_DEFAULT['console']


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
            os.path.relpath(co_filename, settings.BASE_DIR),
            co_name,
            func_lineno,
            content
        )

    def exception(self, e=None, with_stack=True):
        if self.level <= logging.ERROR:
            if e:
                e_type, e_value, traceback_obj = type(e), e, e.__traceback__
            else:
                e_type, e_value, traceback_obj = sys.exc_info()[:3]

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
        self.has_error = False
        super().__init__(tracker.name, *args, **kwargs)

    def set_session_level(self, level):
        self.session_level = level

    def clone(self, with_context=False, catch_exc=False):
        s = self.__class__(self.tracker, with_context=with_context, catch_exc=catch_exc, *self.args, **self.kwargs)
        return s

    def persistent(self):
        if not self.is_empty:
            self.tracker.persistent(self)

    def close(self):
        self.persistent()

    def debug(self, *args, **kwargs):
        return super().debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        if res := super().info(*args, **kwargs):
            if self.session_level < logging.INFO:
                self.set_session_level(logging.INFO)
        return res

    def warn(self, *args, **kwargs):
        if res := super().warn(*args, **kwargs):
            if self.session_level < logging.WARN:
                self.set_session_level(logging.WARN)
        return res

    def error(self, *args, **kwargs):
        if res := super().error(*args, **kwargs):
            self.has_error = True
            if self.session_level < logging.ERROR:
                self.set_session_level(logging.ERROR)
        return res

    def exception(self, *args, **kwargs):
        if res := super().exception(*args, **kwargs):
            self.has_error = True
            if self.session_level < logging.ERROR:
                self.set_session_level(logging.ERROR)
        return res

    def __enter__(self, ):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.exception()
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
            'has_uncritical_error': False
        }

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
        return self.session.warn(*args, **kwargs)

    def error(self, *args, **kwargs):
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.error(*args, **kwargs)
        if res := self.session.error(*args, **kwargs):
            self.context['has_uncritical_error'] = True
            self.set_context_level(logging.WARN)
        return res

    def exception(self, *args, **kwargs):
        kwargs['with_stack'] = kwargs.get('with_stack', True)
        if kwargs.pop('new_session', False):
            with self.new_session() as session:
                return session.exception(*args, **kwargs)
        if res := self.session.exception(*args, **kwargs):
            self.context['has_uncritical_error'] = True
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
            'query_string': None
        }, request={
            'id': None,
            'Header': None,
            'Params': None
        }, response={
            'Header': None,
            'Data': None
        }, api={
            'code': None,
            'message': None,
            'duration': None
        }, user={}, operator={}))

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

    def set_request_headers(self, headers):
        text = json.dumps(headers, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['request']['Header'] = text
        self.console.debug('RequestHeader: %s', text)

    def set_request_params(self, params):
        text = json.dumps(params, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['request']['Params'] = text
        self.console.debug('RequestParams: %s', text)

    def set_response_headers(self, headers):
        text = json.dumps(headers, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['response']['Header'] = text
        self.console.debug('ResponseHeader: %s', text)

    def set_response_data(self, data):
        self.context['api']['code'] = data.get('code')
        self.context['api']['message'] = data.get('message')
        if str(data['code']).startswith('5'):
            self.set_context_level(logging.ERROR)
        elif str(data['code']).startswith('4'):
            self.set_context_level(logging.WARN)
        else:
            self.set_context_level(logging.INFO)

        text = json.dumps(data, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['response']['Data'] = text
        self.console.debug('ResponseData: %s', text)

    def set_http_result(self, info):
        self.context['api']['duration'] = info.get('duration')
        self.context['http']['status_code'] = info.get('status_code')
        text = '%s %s %.1fms %s %s %s' % (
            self.context['http']['method'],
            self.context['http']['url'] if not self.context['http']['query_string'] else '%s?%s' % (
                self.context['http']['url'], self.context['http']['query_string']),
            self.context['api']['duration'],
            self.context['http']['status_code'],
            self.context['api']['code'],
            self.context['api']['message'])

        if self.context['has_error']:
            self.session.error(text)
        elif self.context['has_uncritical_error']:
            self.session.warn(text)
        else:
            self.session.info(text)

    def set_user(self, user):
        if user:
            self.context['user'] = user
        text = json.dumps(self.context['user'], ensure_ascii=False, cls=CustomJsonEncoder)
        self.console.debug('User: %s' % text)

    def set_operator(self, operator):
        if operator:
            self.context['operator'] = operator
        text = json.dumps(self.context['operator'], ensure_ascii=False, cls=CustomJsonEncoder)
        self.console.debug('Operator: %s' % text)

    def get_message(self, session):
        msg = {
            "@version": "1",
            'type': 'HTTPTracker',
            "logger_name": self.name,
            "trace_id": self.trace_id,
            "thread_name": threading.current_thread().getName(),
            "app": settings.APP_NAME,
            "env_name": os.getenv('ENV_NAME', ''),
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
            msg['http'] = self.context['http']
        msg['level'] = get_level_name(msg['level'])
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
            'Params': None,
            'Data': None,
            'duration': None
        }))

    def set_task_info(self, info):
        self.context['execution']['id'] = info['id']
        self.context['task']['name'] = info['name']
        self.context['task']['module'] = info['module']
        self.context['task']['filename'] = info['filename']

    def set_task_params(self, params):
        params = deepcopy(params)
        text = json.dumps(params, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['execution']['Params'] = text

        text = 'task %s.%s received %s' % (
            self.context['task']['module'],
            self.context['task']['name'],
            self.context['execution']['Params']
        )
        self.console.info(text)

        self.console.debug('Execution ID: %s' % self.context['execution']['id'])
        self.console.debug('TaskParams: %s' % self.context['execution']['Params'])

    def set_task_data(self, data):
        data = deepcopy(data)
        text = json.dumps(data, ensure_ascii=False, cls=CustomJsonEncoder)
        self.context['execution']['Data'] = text

        self.console.debug('TaskData: %s' % self.context['execution']['Data'])

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
        elif self.context['has_uncritical_error']:
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
            "app": settings.APP_NAME,
            "env_name": os.getenv('ENV_NAME', ''),
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
            msg['task'] = self.context['task']
        msg['level'] = get_level_name(msg['level'])
        return msg
