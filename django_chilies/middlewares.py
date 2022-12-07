import functools
from time import time

from django.conf import settings
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

from . import trackers
from .settings import TRACKER_DEFAULT
from .trackers import HTTPTracker
from .utils import generate_uuid, headers_dict


def _request_task_apply_async(request, task, *args, **kwargs):
    if 'headers' in kwargs:
        kwargs['headers']['headers']['_trace_id'] = request.tracker.trace_id
    else:
        kwargs['headers'] = {'headers': {'_trace_id': request.tracker.trace_id}}
    return task.apply_async(*args, **kwargs)


def _request_task_delay(request, task, *args, **kwargs):
    return _request_task_apply_async(request, task, args, kwargs)


class TrackerMiddleware(MiddlewareMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_request(self, request):
        request.timer = time()
        request.id = self.get_request_id(request)
        trace_id = self.get_trace_id(request)

        # 实例化http tracker
        tracker_name = settings.DJANGO_CHILIES_TRACKER.get('http_tracker') or TRACKER_DEFAULT['http_tracker']
        request.tracker: HTTPTracker = trackers.instance_from_settings(tracker_name, trace_id=trace_id)
        assert isinstance(request.tracker, HTTPTracker)
        request.tracker.set_request_id(request.id)

        # http info
        http_info = self.__get_http_info(request)
        request.tracker.set_http_info(self.filter_tracked_http_info(request, http_info))
        # request headers
        request_headers = headers_dict(request.headers.__dict__['_store'])
        request.tracker.set_request_headers(self.filter_tracked_request_headers(request, request_headers))

        # celery tasks with request
        request.delay = functools.partial(_request_task_delay, request)
        request.apply_async = functools.partial(_request_task_apply_async, request)

    def process_response(self, request, response):
        # response headers
        request.tracker.set_response_headers(self.filter_tracked_response_headers(request, response, response._headers))
        # http result
        http_result = self.__get_http_result(request, response)
        request.tracker.set_http_result(self.filter_tracked_http_result(request, response, http_result))
        request.tracker.persistent()
        return response

    def process_exception(self, request, exception):
        request.tracker.set_error(exception)
        raise exception

    def __get_http_info(self, request):
        """
        :param request:
        :return:
        """
        try:
            url_name = (url := resolve(request.path)).url_name
            url_namespace = url.namespace
        except:
            url_name = None
            url_namespace = None
        info = {
            'method': request.method,
            'url': request.path,
            'url_name': url_name,
            'url_namespace': url_namespace,
            'query_string': request.META['QUERY_STRING'],
        }

        return info

    def __get_http_result(self, request, response):
        """

        :param request:
        :param response:
        :return:
        """
        result = {
            'status_code': response.status_code,
            'duration': (time() - request.timer) * 1000
        }

        return result

    def get_request_id(self, request):
        """
        to be override
        :param request:
        :return:
        """
        return request.META.get('HTTP_H_TRACE_ID') or generate_uuid(request.timer, uppercase=False, length=32)

    def get_trace_id(self, request):
        """
        to be override
        :param request:
        :return:
        """
        return request.id

    def filter_tracked_http_info(self, request, o):
        """
        to be override
        :param request:
        :param o:
        :return:
        """

        return o

    def filter_tracked_request_headers(self, request, o):
        """
        to be override, remove sensitive keys from headers dict
        :param request:
        :param o:
        :return:
        """
        if 'Cookie' in o:
            o['Cookie'] = ''
        if 'Authorization' in o:
            o['Authorization'] = ''

        return o

    def filter_tracked_response_headers(self, request, response, o):
        """
        to be override, remove sensitive keys from headers dict
        :param request:
        :param response:
        :param o:
        :return:
        """
        if 'Set-Cookie' in o:
            o['Set-Cookie'] = ''

        return o

    def filter_tracked_http_result(self, request, response, o):
        """
        to be override
        :param request:
        :param response:
        :param o:
        :return:
        """

        return o
