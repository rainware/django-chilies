import logging

from django_chilies import errors
from django_chilies.controllers import TrackedController
from rest_framework import serializers

from bookstore.models import Author, Book

from django_chilies.serializers import BlankableIntegerField
from bookstore.tasks import test_tracker

from django_chilies.utils import exception_transfer
from libs.errors import DingServiceError, ding_operator


class RequestSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    author_id = BlankableIntegerField(required=False, allow_null=True, allow_blank=True)
    offset = serializers.IntegerField(min_value=0, required=False, default=0)
    limit = serializers.IntegerField(min_value=1, required=False, default=10)


ResponseSerializer = Book.serializer_class(
    related={
        'author': Author.serializer()
    },
    paging=True
)


class ListBooksController(TrackedController):
    method = 'GET'
    request_serializer_cls = RequestSerializer
    response_serializer_cls = ResponseSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self):
        filters = {}
        if self.params.get('q'):
            filters['name__icontains'] = self.params.get('q')
        if self.params.get('author_id'):
            filters['author'] = self.params.get('author_id')

        rs = Book.prefetch_related('author').filter(**filters)

        self.delay(test_tracker, 1)

        # self.ding()

        return ResponseSerializer(
            rs,
            offset=self.params['offset'],
            limit=self.params['limit'],
        )

    @exception_transfer(DingServiceError)
    # @ding_operator
    def ding(self):
        1 / 0
