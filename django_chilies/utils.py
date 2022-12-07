import datetime
import hashlib
import importlib
import json
import random
import threading
import time
from json import JSONEncoder

from django.forms.utils import to_current_timezone, from_current_timezone


class CustomJsonEncoder(JSONEncoder):
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    TIME_FORMAT = '%H:%M:%S'

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime(self.DATE_FORMAT)
        if isinstance(obj, datetime.time):
            return obj.strftime(self.TIME_FORMAT)

        return super().default(obj)


def deepcopy(o):
    return json.loads(json.dumps(o, cls=CustomJsonEncoder))


def headers_dict(headers):
    d = {}
    for k, v in dict(headers).items():
        d[v[0]] = v[1]
    return d


def generate_uuid(value=None, rand=True, uppercase=True, length=32):
    _uuid = hashlib.md5()
    if value:
        _uuid.update(str(value).encode())
    _uuid.update(time.asctime().encode())
    if rand:
        _uuid.update(str(random.randint(0, 999999999)).encode())
    uuid = _uuid.hexdigest()
    if uppercase:
        uuid = uuid.upper()
    if length < 32:
        uuid = uuid[:length]
    return uuid


def singleton_class(post_init=None):
    def _dec(cls):
        def _init(func):
            def __init(self, *args, **kwargs):
                result = func(self, *args, **kwargs)
                # 在__init__函数执行后，执行post_init
                if post_init:
                    post_init(self)
                return result

            return __init

        cls.__init__ = _init(cls.__init__)
        cls._origin_new = cls.__new__
        cls._origin_init = cls.__init__

        def _singleton_new__(_cls, *args, **kwargs):
            if not hasattr(cls, "_instance"):
                with cls._instance_lock:
                    if not hasattr(cls, "_instance"):
                        cls._instance = cls._origin_new(cls)
                        # 确保__init__函数只会被调用一次
                        cls._instance._origin_init(*args, **kwargs)
            return cls._instance

        cls._instance_lock = threading.Lock()
        cls.__new__ = staticmethod(_singleton_new__)
        # 确保__init__函数只会被调用一次
        cls.__init__ = lambda self, *args, **kwargs: None
        return cls

    return _dec


def get_func(func_name):
    """
    根据func_name反射得到func
    :param func_name:例如apps.api.tasks.request_info
    :return:
    """
    rs = func_name.rsplit('.', 1)
    if len(rs) == 2:
        return getattr(importlib.import_module(rs[0]), rs[1])
    else:
        return eval(func_name)


def time_to_current_timezone(value):
    day = datetime.date(1971, 1, 1)
    dt = to_current_timezone(datetime.datetime.combine(day, value, tzinfo=pytz.utc))
    return dt.time()


def time_from_current_timezone(value):
    day = datetime.date(1971, 1, 1)
    dt = from_current_timezone(datetime.datetime.combine(day, value)).astimezone(pytz.utc)
    return dt.time()
