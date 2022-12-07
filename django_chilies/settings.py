import json

TRACKER_DEFAULT = {
    'buffer_size': 1000,
    'level': 'INFO',
    'console': 'django',  # default console logger
    'http_tracker': 'http-tracker',
    'task_tracker': 'task-tracker',
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
        }
    },
    'trackers': {
        'http-tracker': {
            'class': 'django_chilies.trackers.HTTPTracker',
            'level': 'INFO',
            'buffer_size': 1000,
            'console': 'django',  # console logger
            'writers': ['kafka']
        },
        'task-tracker': {
            'class': 'django_chilies.trackers.TaskTracker',
            'level': 'INFO',
            'buffer_size': 1000,
            'console': 'django',  # console logger
            'writers': ['kafka']
        }
    }
}
