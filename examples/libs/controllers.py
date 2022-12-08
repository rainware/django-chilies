from django_chilies.controllers import APIController, ParamsMixin, TrackerMixin


class BaseController(APIController, ParamsMixin, TrackerMixin):
    """
    """

    def before_process(self):
        """
        :return:
        """
        super().before_process()
        # 校验通用参数

        # 校验权限

    def on_success(self):
        """
        :return:
        """
        super().on_success()

    def on_error(self, error):
        """
        :param error:
        :return:
        """
        error = super().on_error(error)

        return error

    def before_response(self):
        """
        :return:
        """
        super().before_response()
