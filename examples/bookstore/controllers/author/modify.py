import logging

from django_chilies import errors
from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin
from rest_framework import serializers

from bookstore.models import Author


class RequestSerializer(serializers.Serializer):
    age = serializers.IntegerField(required=False, default=None, allow_null=True)


class ModifyAuthorController(APIController, ParamsMixin):
    method = 'PUT'
    request_serializer_cls = RequestSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, author_id):
        author = Author.get(pk=author_id)
        author.update(_refresh=False, age=self.params['age'])
