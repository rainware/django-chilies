import logging

from django_chilies import errors
from django_chilies.controllers import ParamsWrappedController
from rest_framework import serializers

from bookstore.models import Author


class RequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=16)
    age = serializers.IntegerField(required=False, default=None, allow_null=True)


ResponseSerializer = Author.serializer_class(include=['id'])


class CreateAuthorController(ParamsWrappedController):
    method = 'POST'
    request_serializer_cls = RequestSerializer
    response_serializer_cls = ResponseSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self):
        if Author.filter(name=self.params['name']).exists():
            raise errors.ResourceAlreadyExist(self.params['name'])
        author = Author.create(
            name=self.params['name'],
            age=self.params['age'],
        )

        return ResponseSerializer(author)

    def on_error(self, error):
        if not isinstance(error, errors.APIError):
            logging.getLogger('django.server').exception(error)
