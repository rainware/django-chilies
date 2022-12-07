from django_chilies.controllers import TrackedController


class BaseController(TrackedController):
    """
    """

    def before_process(self):
        """
        :return:
        """
        # 校验通用参数

        # 校验权限

    def on_success(self):
        """
        :return:
        """

    def on_error(self, error=None):
        """
        :param error:
        :return:
        """

    def before_response(self):
        """
        :return:
        """
