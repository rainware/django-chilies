import json
import logging
import sys

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from libs.utils import trace_error
from .settings import get_writers_config, get_default_level
from .utils import singleton_class, get_func, JSONEncoder

writers_config = get_writers_config()
default_level = get_default_level()

default_logger = logging.getLogger('django.server')


def instance_from_settings(name):
    assert name in writers_config, 'writer config not exist: %s' % name
    config = writers_config[name]
    cls = get_func(config['class'])

    if 'level' not in config:
        return cls(name=name, level=default_level, **config)
    else:
        return cls(name=name, **config)


class Writer(object):

    def __init__(self, name='', level=logging.NOTSET, *args, **kwargs):
        if not isinstance(level, int):
            level = logging.getLevelName(level)
        self.level = level
        self.name = name

    def write(self, o):
        raise NotImplementedError()

    def is_enabled_for(self, level):
        if not isinstance(level, int):
            level = logging.getLevelName(level)
        return self.level <= level

    def flush(self):
        raise NotImplementedError()


# @singleton_class()
class KafkaWriter(Writer):
    _producers = {}

    def __init__(self, name='', producer=None, topic=None, level=None, *args, **kwargs):
        super().__init__(name=name, level=level, *args, **kwargs)
        self.topic = topic
        if name in self._producers:
            self.producer = self._producers[name]
        else:
            try:
                self.producer = KafkaProducer(**producer)
                self._producers[name] = self.producer
            except NoBrokersAvailable:
                trace_error(logger=default_logger)
                self.producer = None

    def write(self, o):
        if not self.producer:
            return
        level = o.get('level')
        if level and not self.is_enabled_for(level):
            return
        self.producer.send(self.topic, o)

    def flush(self):
        """
        :return:
        """


class SystemWriter(Writer):
    def __init__(self, name='', level=None, redirect_stderr=False, *args, **kwargs):
        super().__init__(name=name, level=level, *args, **kwargs)
        self.redirect_stderr = redirect_stderr

    def write(self, o):
        out = sys.stdout

        level = o.get('level')
        if level:
            if not isinstance(level, int):
                level = logging.getLevelName(level)
            if not self.is_enabled_for(level):
                return
            if level >= logging.ERROR:
                out = sys.stderr

        if self.redirect_stderr:
            out = sys.stdout
        out.write(json.dumps(o, indent=2, ensure_ascii=False, cls=JSONEncoder))

    def flush(self):
        sys.stdout.flush()
        sys.stderr.flush()
