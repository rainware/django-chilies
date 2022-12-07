import sys


class APICode(object):
    _MESSAGE_INDEX = 1

    SUCCESS = (200, ('SUCCESS', '成功'))
    PARAM_ERROR = (400, ('Invalid Params', '参数错误'))
    ACCESS_FORBIDDEN = (4003, ('Access Forbidden', '您没有权限进行操作'))
    RESOURCE_NOT_EXIST = (404, ('Resource Not Exist', '资源不存在'))
    OPERATION_NOT_ALLOWED = (4005, ('Operation Not Allowed', '操作不被允许'))
    RESOURCE_ALREADY_EXIST = (409, ('Resource Already Exist', '资源已存在'))
    FIELD_OCCUPIED = (4009, ('Field Occupied', '字段被占用'))
    INTERNAL_SERVER_ERROR = (500, ('Internal Server Error', '服务器内部错误'))

    @classmethod
    def get(cls, item):
        return item[0], item[1][cls._MESSAGE_INDEX]


class Error(Exception):
    api_code = APICode.SUCCESS

    def __init__(self, *args, **kwargs):
        extra = kwargs.pop('extra', None)
        super().__init__(*args, **kwargs)
        self.code, self.message = APICode.get(self.api_code)
        if extra is not None:
            self.extra = extra
        else:
            self.extra = {}

    def __str__(self):
        return str(self.__class__)


class APIError(Error):
    """
    接口调用不当，4xx
    """


class ParamError(APIError):
    """
    参数错误 400
    """

    api_code = APICode.PARAM_ERROR

    def __init__(self, *fields, **kwargs):
        super().__init__(self, **kwargs)
        if fields:
            self.message = '%s: %s' % (self.message, ','.join(fields))


class ResourceNotExist(APIError):
    """
    404
    """

    api_code = APICode.RESOURCE_NOT_EXIST

    def __init__(self, content=None, **kwargs):
        super().__init__(self, **kwargs)

        if content:
            self.message = '%s: %s' % (self.message, content)


class ResourceAlreadyExist(APIError):
    """
    409
    """

    api_code = APICode.RESOURCE_ALREADY_EXIST

    def __init__(self, content=None, **kwargs):
        super().__init__(self, **kwargs)

        if content:
            self.message = '%s: %s' % (self.message, content)


class AccessForbidden(APIError):
    """
    4003
    """

    api_code = APICode.ACCESS_FORBIDDEN

    def __init__(self, target=None, **kwargs):
        super().__init__(self, **kwargs)

        if target:
            self.message = '%s: %s' % (self.message, target)


class OperationNotAllowed(APIError):
    """
    4005
    """

    api_code = APICode.OPERATION_NOT_ALLOWED

    def __init__(self, content=None, **kwargs):
        super().__init__(self, **kwargs)

        if content:
            self.message = '%s: %s' % (self.message, content)


class FieldOccupied(APIError):
    """
    4009
    """

    api_code = APICode.FIELD_OCCUPIED

    def __init__(self, content=None, **kwargs):
        super().__init__(self, **kwargs)

        if content:
            self.message = '%s: %s' % (self.message, content)


class InternalServerError(Error):
    """
    服务器内部错误，5xx
    """

    api_code = APICode.INTERNAL_SERVER_ERROR

    def __init__(self, *args, **kwargs):
        """
        """
        # Exception.__init__(self, *args, **kwargs)
        super().__init__(*args, **kwargs)
        e_type, e_value, e_trackback = sys.exc_info()

        if e_type:
            self.extra['e_type'] = e_type.__name__
            self.extra['e_value'] = str(e_value)
        else:
            self.extra['e_type'] = str(type(self))
            self.extra['e_value'] = str(self)
