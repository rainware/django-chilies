import inspect
import os
import time
import functools
import traceback

from celery import Task, signals, Celery as _OriginalCelery
from celery.exceptions import Retry
from celery.utils import gen_task_name

from . import trackers
from .settings import get_task_tracker_fmts, get_task_tracker_config
from .trackers import TaskTracker
from .utils import generate_uuid, deepcopy


class Celery(_OriginalCelery):

    def tracked_task(self, *args, **kwargs):
        def _dec(func):
            kwargs['bind'] = True
            return self.task(*args, **kwargs)(task_tracker()(func))

        return _dec


def task_tracker():
    def _dec(func):

        @functools.wraps(func)
        def __dec(*args, **kwargs):
            s_time = time.time()
            # 实例化task tracker
            tracker_config = get_task_tracker_config()
            tracker: TaskTracker = trackers.instance_from_settings(tracker_config['tracker'])
            assert isinstance(tracker, TaskTracker)
            task = None
            trace_id = None
            headers = None
            if args and isinstance(args[0], Task):
                task = args[0]
                headers = task.request.headers
                execution_id = task.request.id or generate_uuid(s_time, uppercase=False, length=32)
                if headers:
                    trace_id = headers.get('_trace_id', execution_id)
            else:
                execution_id = generate_uuid(s_time, uppercase=False, length=32)
            trace_id = trace_id or execution_id
            tracker.set_trace_id(trace_id)
            try:
                tracker.set_task_info({
                    'id': execution_id,
                    'name': func.__name__,
                    'module': func.__module__,
                    'filename': os.path.normcase(func.__code__.co_filename),
                })
                if headers is not None:
                    fmts = get_task_tracker_fmts('execution.header', tracker_config)
                    if fmts:
                        tracker.set_task_headers(deepcopy(headers), formats=fmts)
                fmts = get_task_tracker_fmts('execution.params', tracker_config)
                if fmts:
                    try:
                        tracker.set_task_params(deepcopy({
                            'args': args[1:] if task else args,
                            'kwargs': kwargs
                        }), formats=fmts)
                    except TypeError as e:
                        tracker.warn('JSON serialization error: {}'.format(str(e)))
                if task:
                    task.tracker = tracker
                else:
                    kwargs['tracker'] = tracker
                res = func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, Retry):
                    # 手动retry
                    tracker.error(str(e))
                elif isinstance(e, getattr(task, 'autoretry_for', tuple())) and task.request.retries < task.max_retries:
                    # auto_retry
                    tracker.exception(e)
                else:
                    tracker.set_error(e)
                raise
            else:
                if res is not None:
                    fmts = get_task_tracker_fmts('execution.data', tracker_config)
                    if fmts:
                        tracker.set_task_data(deepcopy(res), formats=fmts)
            finally:
                e_time = time.time()
                tracker.set_task_result({
                    'duration': (e_time - s_time) * 1000
                })
                tracker.persistent()
            return res

        return __dec

    return _dec


class _Task(Task):

    def __init__(self, handler_cls, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler_cls = handler_cls

    def run(self, *args, **kwargs):
        handler = self.handler_cls()
        return handler.run(*args, **kwargs)


class TaskHandler(object):
    task__name = None
    task_cls = None
    task = None

    @classmethod
    def as_task(cls, module=None):
        if cls.task:
            return cls.task

        cls_name = cls.__name__
        # 设置module，默认是django_chilies.celery
        if not module:
            # 获取本函数调用者所在的module
            module = module_obj.__name__ if (module_obj := inspect.getmodule(inspect.stack()[1][0])) else None
        module = module or cls.__module__

        # cls.task__name = cls.task__name or gen_task_name(_Task.app, cls.__name__, module)

        # task class vars
        task_vars = {'__module__': module}
        var_name_prefix = 'task__'
        for var_name in dir(cls):
            if var_name.startswith(var_name_prefix):
                task_var_name = var_name[len(var_name_prefix):]
                task_vars[task_var_name] = getattr(cls, var_name)
        # create task class
        task_cls = type(cls_name, (_Task,), task_vars)
        # set reference
        cls.task_cls = task_cls
        cls.task = task_cls(cls)
        return cls.task

    @classmethod
    def get_task(cls):
        return cls.task

    @classmethod
    def get_task_name(cls):
        return cls.task.name

    def __init__(self, *args, **kwargs):
        self.timer = time.time()

        # self.task = task
        self.request = self.task.request

        # 实例化task tracker
        self.execution_id = self.request.id or generate_uuid(self.timer, uppercase=False, length=32)
        if self.request.headers:
            self.trace_id = self.request.headers.get('_trace_id', self.execution_id)
        else:
            self.trace_id = self.execution_id
        self.tracker_config = get_task_tracker_config()
        self.tracker: TaskTracker = trackers.instance_from_settings(self.tracker_config['tracker'],
                                                                    trace_id=self.trace_id)
        assert isinstance(self.tracker, TaskTracker)

    def run(self, *args, **kwargs):
        try:
            task_module, task_name = self.task.name.rsplit('.', 1)
            self.tracker.set_task_info({
                'id': self.execution_id,
                'name': task_name,
                'module': task_module,
                'filename': inspect.getfile(self.__class__)
            })
            if self.request.headers is not None:
                fmts = get_task_tracker_fmts('execution.header', self.tracker_config)
                if fmts:
                    self.tracker.set_task_headers(deepcopy(self.request.headers), formats=fmts)
            fmts = get_task_tracker_fmts('execution.params', self.tracker_config)
            if fmts:
                try:
                    self.tracker.set_task_params(deepcopy({'args': args, 'kwargs': kwargs}), formats=fmts)
                except TypeError as e:
                    self.tracker.warn('JSON serialization error: {}'.format(str(e)))
            res = self.process(*args, **kwargs)
        except Exception as e:
            if isinstance(e, Retry):
                # 手动retry
                self.tracker.error(str(e))
            elif isinstance(e, getattr(self.task, 'autoretry_for', tuple())) and self.request.retries < self.task.max_retries:
                # auto_retry
                self.tracker.exception(e)
            else:
                self.tracker.set_error(e)
            raise
        else:
            if res is not None:
                fmts = get_task_tracker_fmts('execution.data', self.tracker_config)
                if fmts:
                    self.tracker.set_task_data(deepcopy(res), formats=fmts)
        finally:
            self.tracker.set_task_result({
                'duration': (time.time() - self.timer) * 1000
            })
            self.tracker.persistent()
        return res

    def process(self, *args, **kwargs):
        raise NotImplementedError()

    def delay(self, task, *args, **kwargs):
        return self.apply_async(task, args, kwargs)

    def apply_async(self, task, *args, **kwargs):
        if isinstance(task, str):
            task = self.task.app.tasks[task]
        if 'headers' in kwargs:
            kwargs['headers']['headers']['_trace_id'] = self.tracker.trace_id
        else:
            kwargs['headers'] = {'headers': {'_trace_id': self.tracker.trace_id}}
        return task.apply_async(*args, **kwargs)

    def si(self, task, *args, **kwargs):
        headers = kwargs.pop('headers', {})
        headers['_trace_id'] = self.tracker.trace_id
        return task.si(*args, **kwargs).set(headers={'headers': headers})

    def s(self, task, *args, **kwargs):
        headers = kwargs.pop('headers', {})
        headers['_trace_id'] = self.tracker.trace_id
        return task.s(*args, **kwargs).set(headers={'headers': headers})
