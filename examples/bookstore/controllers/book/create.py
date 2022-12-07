from django_chilies.controllers import TrackedController
from rest_framework import serializers

from bookstore.models import Author, Book


class RequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=32)
    author_id = serializers.IntegerField()


ResponseSerializer = Book.serializer_class(include=['id'])


class CreateBookController(TrackedController):
    method = 'POST'
    request_serializer_cls = RequestSerializer
    response_serializer_cls = ResponseSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self):
        author = Author.get(pk=self.params['author_id'])
        book = Book.create(
            name=self.params['name'],
            author=author,
        )

        return ResponseSerializer(book)


