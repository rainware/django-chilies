import logging

from django_chilies import errors
from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin

from bookstore.models import Book


class DeleteBookController(APIController, ParamsMixin, TrackerMixin):
    method = 'DELETE'

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, book_id):
        book = Book.get(pk=book_id)
        book.delete()
