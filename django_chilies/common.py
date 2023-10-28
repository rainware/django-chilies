import datetime
import json
from collections.abc import KeysView, ValuesView
from json import JSONEncoder
from kombu.utils.json import JSONEncoder as KombuJSONEncoder

from django.utils.encoding import force_str
from django.utils.functional import Promise
from kombu.serialization import register

from .settings import DATETIME_FORMAT, DATE_FORMAT, TIME_FORMAT


class DefaultJSONEncoder(KombuJSONEncoder, JSONEncoder):

    def default(self, obj, *args, **kwargs):
        if isinstance(obj, datetime.datetime):
            return obj.strftime(DATETIME_FORMAT)
        if isinstance(obj, datetime.date):
            return obj.strftime(DATE_FORMAT)
        if isinstance(obj, datetime.time):
            return obj.strftime(TIME_FORMAT)
        if isinstance(obj, Promise):
            return force_str(obj)
        if isinstance(obj, (set, KeysView, ValuesView)):
            return list(obj)

        return super().default(obj, *args, **kwargs)


# def dumps(obj):
#     return json.dumps(obj, cls=DefaultJSONEncoder)
#
#
# def loads(obj):
#     return json.loads(obj)


# register('wrapped-json', dumps, loads,
#          content_type='application/json')
