import logging

from django_chilies import errors
from django_chilies.controllers import TrackedController

from bookstore.models import Author, Book

ResponseSerializer = Book.serializer_class(
    related={
        'author': Author.serializer()
    }
)


class GetBookDetailController(TrackedController):
    method = 'GET'

    response_serializer_cls = ResponseSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, book_id):
        book = Book.select_related('author').get(pk=book_id)
        return ResponseSerializer(book)
