import logging

from django_chilies import errors
from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin
from rest_framework import serializers

from bookstore.models import Author


class RequestSerializer(serializers.Serializer):
    q = serializers.CharField(required=False)
    offset = serializers.IntegerField(min_value=0, required=False, default=0)
    limit = serializers.IntegerField(min_value=1, required=False, default=10)


ResponseSerializer = Author.serializer_class(paging=True)


class ListAuthorsController(APIController, ParamsMixin):
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

        rs = Author.filter(**filters)
        # 1/0
        return ResponseSerializer(
            rs,
            offset=self.params['offset'],
            limit=self.params['limit'],
        )

        # return ModelLessPaginationSerializer({
        #     'rows': [{'name': 'zhangsan', 'age': 30}],
        #     'total': 1
        # })

