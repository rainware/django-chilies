import logging

from django_chilies import errors
from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin
from rest_framework import serializers

from bookstore.models import Author, Book


class RequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    author_id = serializers.IntegerField(required=False)


class ModifyBookController(APIController, ParamsMixin, TrackerMixin):
    method = 'PATCH'
    request_serializer_cls = RequestSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, book_id):
        book = Book.get(pk=book_id)
        update_data = {}
        if 'name' in self.params:
            update_data['name'] = self.params['name']
        if 'author_id' in self.params:
            update_data['author'] = Author.get(pk=self.params['author_id'])
        if update_data:
            book.update(_refresh=False, **update_data)
