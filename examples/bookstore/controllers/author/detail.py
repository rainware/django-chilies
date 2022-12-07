
from bookstore.models import Author

from django_chilies.controllers import ParamsWrappedController

ResponseSerializer = Author.serializer_class()


class GetAuthorDetailController(ParamsWrappedController):
    method = 'GET'

    response_serializer_cls = ResponseSerializer

    # 可以注释这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, author_id):
        author = Author.get(pk=author_id)
        return ResponseSerializer(author)
