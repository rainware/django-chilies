from django.conf import settings

from django_chilies.trackers import HTTPTracker, TaskTracker


class CustomHTTPTracker(HTTPTracker):

    def filter_message(self, o):
        o['app_name'] = settings.APP_NAME
        return o


class CustomTaskTracker(TaskTracker):

    def filter_message(self, o):
        o['app_name'] = settings.APP_NAME
        return o
