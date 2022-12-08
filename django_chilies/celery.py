import os
import time
import functools
from celery import Task

from . import trackers
from .settings import get_task_tracker_fmts, get_task_tracker_config
from .trackers import TaskTracker
from .utils import generate_uuid, deepcopy

app = None


def wraps(_app):
    global app
    app = _app
    app.tracked_task = tracked_task
    return app


def tracked_task(*args, **kwargs):
    kwargs['bind'] = True

    def _dec(func):
        return app.task(*args, **kwargs)(task_tracker()(func))

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
            bind_task = False
            trace_id = None
            headers = None
            if args and isinstance(args[0], Task):
                headers = args[0].request.headers
                bind_task = True
                task_id = args[0].request.id
                if headers:
                    trace_id = headers.get('_trace_id', task_id)
            else:
                task_id = generate_uuid(s_time, uppercase=False, length=32)
            trace_id = trace_id or task_id
            tracker.set_trace_id(trace_id)
            try:
                tracker.set_task_info({
                    'id': task_id,
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
                    tracker.set_task_params(deepcopy({
                        'args': args[1:] if bind_task else args,
                        'kwargs': kwargs
                    }), formats=fmts)
                if bind_task:
                    args[0].tracker = tracker
                else:
                    kwargs['tracker'] = tracker
                res = func(*args, **kwargs)
            except Exception as e:
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
