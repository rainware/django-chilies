import logging

from django.conf import settings
from kafka import KafkaProducer

from .settings import TRACKER_DEFAULT
from .utils import singleton_class, get_func

writers_config = dict(TRACKER_DEFAULT['writers'], **settings.DJANGO_CHILIES_TRACKER.get('writers', {}))
default_level = settings.DJANGO_CHILIES_TRACKER.get('level') or TRACKER_DEFAULT['level']


def instance_from_settings(name):
    assert name in writers_config, 'writer config not exist: %s' % name
    config = writers_config[name]
    cls = get_func(config['class'])

    if 'level' not in config:
        return cls(level=default_level, **config)
    else:
        return cls(**config)


class Writer(object):

    def __init__(self, level=logging.NOTSET, *args, **kwargs):
        if not isinstance(level, int):
            level = logging.getLevelName(level)
        self.level = level

    def write(self, o):
        raise NotImplementedError()

    def is_enabled_for(self, level):
        if not isinstance(level, int):
            level = logging.getLevelName(level)
        return self.level <= level

    def flush(self):
        raise NotImplementedError()


@singleton_class()
class KafkaWriter(Writer):

    def __init__(self, producer=None, topic=None, level=None, *args, **kwargs):
        super().__init__(level=level, *args, **kwargs)
        self.topic = topic
        self.producer = KafkaProducer(**producer)

    def write(self, o):
        if (level := o.get('level')) and not self.is_enabled_for(level):
            return
        self.producer.send(self.topic, o)

    def flush(self):
        """
        :return:
        """
