import sys
from django.utils.translation import gettext_lazy as _


class Code(object):
    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __eq__(self, other):
        if isinstance(other, int):
            return self.code == other
        return self.code == other.code


class APICodes(object):

    SUCCESS = Code(200, _('Success'))
    PARAM_ERROR = Code(400, _('Params Invalid'))
    ACCESS_FORBIDDEN = Code(4003, _('Access Forbidden'))
    RESOURCE_NOT_EXIST = Code(404, _('Resource Not Exist'))
    OPERATION_NOT_ALLOWED = Code(4005, _('Operation Not Allowed'))
    RESOURCE_ALREADY_EXIST = Code(409, _('Resource Already Exist'))
    FIELD_OCCUPIED = Code(4009, _('Field Occupied'))
    INTERNAL_SERVER_ERROR = Code(500, _('Internal Server Error'))


class Error(Exception):
    CODE = APICodes.SUCCESS

    def __init__(self, content=None, *args, **kwargs):
        self.code, self.message = self.CODE.code, self.CODE.message
        if content:
            self.message = '%s: %s' % (self.message, content)
        extra = kwargs.pop('extra', None)
        if extra is not None:
            self.extra = extra
        else:
            self.extra = {}

        super().__init__(self.message, *args, **kwargs)


class APIError(Error):
    """
    接口调用不当，4xx
    """


class ParamError(APIError):
    """
    参数错误 400
    """

    CODE = APICodes.PARAM_ERROR

    def __init__(self, *fields, **kwargs):
        content = ','.join(fields)
        super().__init__(content, **kwargs)


class ResourceNotExist(APIError):
    """
    404
    """

    CODE = APICodes.RESOURCE_NOT_EXIST


class ResourceAlreadyExist(APIError):
    """
    409
    """

    CODE = APICodes.RESOURCE_ALREADY_EXIST


class AccessForbidden(APIError):
    """
    4003
    """

    CODE = APICodes.ACCESS_FORBIDDEN


class OperationNotAllowed(APIError):
    """
    4005
    """

    CODE = APICodes.OPERATION_NOT_ALLOWED


class FieldOccupied(APIError):
    """
    4009
    """

    CODE = APICodes.FIELD_OCCUPIED


class InternalServerError(Error):
    """
    服务器内部错误，5xx
    """

    CODE = APICodes.INTERNAL_SERVER_ERROR

    def __init__(self, *args, **kwargs):
        """
        """
        super().__init__(*args, **kwargs)

        e_type, e_value, e_trackback = sys.exc_info()
        if e_type:
            self.extra['e_type'] = e_type.__name__
            self.extra['e_value'] = str(e_value)
        else:
            self.extra['e_type'] = str(type(self))
            self.extra['e_value'] = str(self)
