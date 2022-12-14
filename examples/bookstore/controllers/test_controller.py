from rest_framework.response import Response

from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin


class TestController(APIController):
    method = 'GET'

    # 可以注释掉这两行看看效果
    view__authentication_classes = []
    view__permission_classes = []

    def process(self, *args, **kwargs):
        b = self.request.GET.get('a')
        return Response({'b': b})
