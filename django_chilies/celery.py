import os
import time
import functools
from celery import Task
from django.conf import settings

from . import trackers
from .settings import DEFAULT
from .trackers import TaskTracker
from .utils import generate_uuid

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
            tracker_name = getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('task_tracker') or DEFAULT['TRACKER']['task_tracker']
            tracker: TaskTracker = trackers.instance_from_settings(tracker_name)
            assert isinstance(tracker, TaskTracker)
            bind_task = False
            trace_id = None
            if args and isinstance(args[0], Task):
                bind_task = True
                task_id = args[0].request.id
                if args[0].request.headers:
                    trace_id = args[0].request.headers.get('_trace_id', task_id)
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
                tracker.set_task_params({
                    'args': args[1:] if bind_task else args,
                    'kwargs': kwargs
                })
                if bind_task:
                    args[0].tracker = tracker
                else:
                    kwargs['tracker'] = tracker
                res = func(*args, **kwargs)
            except:
                tracker.set_error()
                raise
            else:
                tracker.set_task_data(res)
            finally:
                e_time = time.time()
                tracker.set_task_result({
                    'duration': (e_time - s_time) * 1000
                })
                tracker.persistent()
            return res

        return __dec

    return _dec
