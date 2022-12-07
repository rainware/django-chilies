from examples.celery import app as celery_app

from django_chilies.celery import task_tracker


@celery_app.tracked_task()
def test_tracker(self, a):
    self.tracker.info(self.request.headers)
    self.tracker.info(a, new_session=True)
    with self.tracker.new_session(catch_exc=True) as session:
        session.info('new session')
        1 / 0
        session.warn('new session warning')
    {}['abc']


@celery_app.task()
@task_tracker()             # as you wish
def test_tracker_x(a, tracker=None):
    tracker.info(a)
    with tracker.new_session() as session:
        session.info('new session')
        1 / 0
        session.warn('new session warning')
    {}['abc']
    pass
