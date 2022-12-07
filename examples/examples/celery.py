import os
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'examples.settings')

# app definition
app = Celery('examples')
app.config_from_object('django.conf:settings', namespace='CELERY')
# 配置定时器模块

app.autodiscover_tasks()


from django_chilies.celery import wraps
app = wraps(app)
