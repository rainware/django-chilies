from django_chilies.errors import APICodes, InternalServerError
from django_chilies.utils import exception_transfer


class ErrorCodes(APICodes):
    DING_SERVICE_ERROR = (5022, ('DingDing Service Error', 'Dingding服务调用错误'))


class DingServiceError(InternalServerError):
    """
    调用dingding service错误
    """

    api_code = ErrorCodes.DING_SERVICE_ERROR


def ding_operator(func):
    return exception_transfer(DingServiceError)(func)
