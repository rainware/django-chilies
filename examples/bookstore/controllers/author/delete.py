import logging

from django.db.models import ProtectedError

from django_chilies import errors
from django_chilies.controllers import ParamsWrappedController

from bookstore.models import Author


class DeleteAuthorController(ParamsWrappedController):
    method = 'DELETE'

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, author_id):
        author = Author.get(pk=author_id)
        try:
            author.delete()
        except ProtectedError as e:
            raise errors.OperationNotAllowed('delete related objects first')

    def on_error(self, error):
        if not isinstance(error, errors.APIError):
            logging.getLogger('django.server').exception(error)
