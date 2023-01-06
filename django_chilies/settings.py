import json

from django.conf import settings

DEFAULT = {
    'JSON_ENCODER': 'django_chilies.utils.JSONEncoder',
    'BASE_DIR': '',  # base path of django project
    'TRACKER': {
        'buffer_size': 1000,
        'level': 'INFO',
        'console': 'django',  # default console logger
        'http_tracker': {
            'tracker': 'http-tracker',
            'request': ['header', 'Header', 'Body', 'params', 'Params'],
            'response': ['header', 'Header', 'Body', 'data', 'Data']
        },
        'task_tracker': {
            'tracker': 'task-tracker',
            'execution': ['header', 'Header', 'params', 'Params', 'data', 'Data']
        },
        'writers': {
            'kafka': {
                'class': 'django_chilies.writers.KafkaWriter',
                'level': 'INFO',
                'topic': 'tracker',
                'producer': {
                    'bootstrap_servers': ['127.0.0.1:9092'],
                    'security_protocol': 'PLAINTEXT',
                    'value_serializer': lambda msg: json.dumps(msg, ensure_ascii=False).encode("utf-8"),
                }
            },
            'system': {
                'class': 'django_chilies.writers.SystemWriter',
                'level': 'INFO',
                'redirect_stderr': False

            }
        },
        'trackers': {
            'http-tracker': {
                'class': 'django_chilies.trackers.HTTPTracker',
                'level': 'INFO',
                'buffer_size': 1000,
                'console': 'django',  # console logger
                'writers': ['system']
            },
            'task-tracker': {
                'class': 'django_chilies.trackers.TaskTracker',
                'level': 'INFO',
                'buffer_size': 1000,
                'console': 'django',  # console logger
                'writers': ['system']
            }
        }
    }
}


def get_json_encoder():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('JSON_ENCODER') or DEFAULT['JSON_ENCODER']


def get_base_dir():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('BASE_DIR') or DEFAULT['BASE_DIR']


def get_http_tracker_config():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('http_tracker') or DEFAULT['TRACKER'][
        'http_tracker']


def get_task_tracker_config():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('task_tracker') or DEFAULT['TRACKER'][
        'task_tracker']


def get_writers_config():
    return dict(DEFAULT['TRACKER']['writers'],
                **getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('writers', {}))


def get_default_level():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('level') or DEFAULT['TRACKER']['level']


def get_default_buffer_size():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('buffer_size') or DEFAULT['TRACKER'][
        'buffer_size']


def get_default_console():
    return getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('console') or DEFAULT['TRACKER']['console']


def get_trackers_config():
    return dict(DEFAULT['TRACKER']['trackers'],
                **getattr(settings, 'DJANGO_CHILIES', {}).get('TRACKER', {}).get('trackers', {}))


def get_http_tracker_fmts(_type, config=None):
    """
    :param _type: request.header, request.params, request.body
                    response.header, response.data, response.body
    :param config:
    :return:
    """
    k1, k2 = _type.split('.')
    if config is None:
        config = get_http_tracker_config()
    fmts = []
    if k2 == 'header':
        for item in config.get(k1, []):
            if item == 'header':
                fmts.append('json')
            elif item == 'Header':
                fmts.append('text')
    elif k2 == 'params':
        for item in config.get(k1, []):
            if item == 'params':
                fmts.append('json')
            elif item == 'Params':
                fmts.append('text')
    elif k2 == 'data':
        for item in config.get(k1, []):
            if item == 'data':
                fmts.append('json')
            elif item == 'Data':
                fmts.append('text')
    elif k2 == 'body':
        for item in config.get(k1, []):
            if item == 'Body':
                fmts.append('text')
    else:
        raise Exception()

    return fmts


def get_task_tracker_fmts(_type, config=None):
    """
    :param _type: execution.header, execution.params, execution.data
    :param config:
    :return:
    """
    k1, k2 = _type.split('.')
    if config is None:
        config = get_task_tracker_config()
    fmts = []
    if k2 == 'header':
        for item in config.get(k1, []):
            if item == 'header':
                fmts.append('json')
            elif item == 'Header':
                fmts.append('text')
    elif k2 == 'params':
        for item in config.get(k1, []):
            if item == 'params':
                fmts.append('json')
            elif item == 'Params':
                fmts.append('text')
    elif k2 == 'data':
        for item in config.get(k1, []):
            if item == 'data':
                fmts.append('json')
            elif item == 'Data':
                fmts.append('text')
    else:
        raise Exception()

    return fmts
