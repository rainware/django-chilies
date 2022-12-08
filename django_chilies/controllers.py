import logging
import sys

from rest_framework import serializers
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response
from rest_framework.views import APIView

from . import errors
from .errors import APICode
from .serializers import PaginationListSerializer, ModelLessPaginationSerializer
from .settings import get_http_tracker_fmts
from .trackers import HTTPTracker
from .utils import deepcopy


class _View(APIView):
    controller_classes = {}

    @classmethod
    def get_controller_class(cls, method):
        return cls.controller_classes.get((cls, method.upper()))

    @classmethod
    def add_controller_class(cls, controller_class):
        method = controller_class.method
        key = (cls, method)
        assert key not in cls.controller_classes, \
            'Duplicated Controller defined: {} {}'.format(method, controller_class.__name__)
        cls.controller_classes[key] = controller_class
        cls.controller_classes[key] = controller_class

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self.__process(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self.__process(*args, **kwargs)

    def put(self, *args, **kwargs):
        return self.__process(*args, **kwargs)

    def patch(self, *args, **kwargs):
        return self.__process(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.__process(*args, **kwargs)

    def __process(self, request, *args, **kwargs):
        controller_class = self.get_controller_class(method=request.method)
        if not controller_class:
            raise MethodNotAllowed(request.method)
        controller = controller_class(self)
        return controller._process(*args, **kwargs)


class ControllerMixin(object):
    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs:
        """

    def before_process(self):
        """
        to be override, before process
        :return:
        """

    def on_success(self):
        """
        to be override, on process success
        :return:
        """
        pass

    def on_error(self, error: Exception) -> Exception:
        """
        to be override, on process error
        :return: return None if error are handled, else Exception
        """

    def before_response(self):
        """
        to be override, before response returned to view
        :return:
        """
        pass

    @classmethod
    def trace_error(cls, error):
        logging.getLogger('django.server').exception(error)


class APIController(ControllerMixin):
    method = None
    view_class = None

    @classmethod
    def get_view_class(cls):
        return cls.view_class

    @classmethod
    def set_view_class(cls, view_class, method=None):
        cls.view_class = view_class
        cls.method = method or cls.method
        view_class.add_controller_class(cls)

    @classmethod
    def as_view(cls):
        """
        :return: APIView.as_view()
        """
        # view类变量，比如authentication_classes/permission_classes
        view_vars = {}
        var_name_prefix = 'view__'
        for var_name in dir(cls):
            if var_name.startswith('view__'):
                view_var_name = var_name[len(var_name_prefix):]
                view_vars[view_var_name] = getattr(cls, var_name)

        view_class = type('View', (_View,), view_vars)
        cls.set_view_class(view_class)
        # 苟富贵 勿相忘
        for sibling in getattr(cls, '_siblings', []):
            sibling.set_view_class(view_class)
        return view_class.as_view()

    @classmethod
    def with_siblings(cls, *siblings):
        """
        :param siblings: 同一个view下的其他method对应的controller
        :return:
        """
        cls._siblings = []
        for sibling in siblings:
            if sibling not in cls._siblings:
                cls._siblings.append(sibling)
        return cls

    def __init__(self, view, *args, **kwargs):
        self.view = view
        self.request = view.request
        self.response = None
        super().__init__(*args, **kwargs)

    def process(self, *args, **kwargs):
        raise NotImplementedError()

    def _process(self, *args, **kwargs):
        try:
            self.before_process()
            self.response = self.process(*args, **kwargs)
        except Exception as e:
            error = self.on_error(e)
            if error:
                raise
        else:
            self.on_success()

        self.before_response()
        return self.response

    def before_process(self):
        """
        to be override, before process
        :return:
        """
        super().before_process()

    def on_success(self):
        """
        to be override, on process success
        :return:
        """
        super().on_success()

    def on_error(self, error: Exception) -> Exception:
        """
        to be override, on process error
        :return:
        """
        error = super().on_error(error)
        if error:
            self.trace_error(error)
        return error

    def before_response(self):
        """
        to be override, before response returned to view
        :return:
        """
        super().before_response()

        if self.response is None:
            self.response = Response(status=500)


class ParamsMixin(ControllerMixin):
    request_serializer_cls = None
    response_serializer_cls = None

    def __init__(self, *args, **kwargs):
        # 未经校验的参数
        self.unvalidated_params = None
        # 经校验的参数
        self.params = None
        # 返回参数
        self.data = None

        super().__init__(*args, **kwargs)

    def before_process(self):
        """
        to be override, before process
        :return:
        """
        # 参数解析
        param_errors = self.__parse_params()
        if param_errors:
            raise errors.ParamError(*list(param_errors.keys()))

        super().before_process()

    def on_success(self):
        """
        to be override, on process success
        :return:
        """
        self.data = self._generate_data(self.response)
        super().on_success()

    def on_error(self, error: Exception) -> Exception:
        """
        to be override, on process error
        :return:
        """
        trace = True
        if isinstance(error, errors.APIError):
            self.data = self._generate_data_by_error(error)
            trace = False
        elif isinstance(error, errors.InternalServerError):
            self.data = self._generate_data_by_error(error)
        else:
            self.data = self._generate_data_by_error(errors.InternalServerError())

        error = super().on_error(error)
        if not error:
            trace = False

        if trace:
            self.trace_error(error)

        return error

    def before_response(self):
        """
        to be override, before response returned to view
        :return:
        """

        self.response = Response(self.data)
        super().before_response()

    def __parse_params(self):
        """
        :return: params error dict
        """
        params = {}
        for k, v in self.request.query_params.lists():
            if k.endswith('[]'):
                params[k[:-2]] = v
            else:
                params[k] = v[-1]
        params.update(self.request.data)
        self.unvalidated_params = params

        # 参数校验
        if self.request_serializer_cls:
            request_serializer = self.request_serializer_cls(data=self.unvalidated_params,
                                                             context={'request': self.request})
            if not request_serializer.is_valid():
                return dict(request_serializer.errors)
            self.params = dict(request_serializer.validated_data)

        return {}

    def _generate_data(self, res):
        code, message = APICode.get(APICode.SUCCESS)
        res_data = {'code': code, 'message': message}
        if isinstance(res, (dict, list, str)):
            res_data['data'] = res
        elif isinstance(res, (PaginationListSerializer, ModelLessPaginationSerializer)):
            res_data['data'] = res.data['rows']
            if res.data['total'] is not None:
                res_data['total'] = res.data['total']
        elif isinstance(res, (serializers.Serializer, serializers.ListSerializer)):
            res_data['data'] = res.data

        return res_data

    def _generate_data_by_error(self, error):
        data = {'code': error.code, 'message': error.message}
        if error.extra:
            data['extra'] = error.extra
        return data


class TrackerMixin(ControllerMixin):

    def __init__(self, *args, **kwargs):
        self.tracker: HTTPTracker = self.request.tracker

        super().__init__(*args, **kwargs)

    def before_process(self):
        if hasattr(self, 'unvalidated_params'):
            fmts = get_http_tracker_fmts('request.params', self.request.tracker_config)
            if fmts:
                self.tracker.set_request_params(
                    self.filter_tracked_params(self.unvalidated_params),
                    formats=fmts
                )
        self.tracker.set_user(self.get_tracked_user())
        self.tracker.set_operator(self.get_tracked_operator())

        super().before_process()

    def on_success(self):
        """
        :return:
        """

        super().on_success()

    def on_error(self, error: Exception) -> Exception:
        if not isinstance(error, errors.APIError):
            self.tracker.set_error(error)

        return super().on_error(error)

    def before_response(self):
        if hasattr(self, 'data'):
            fmts = get_http_tracker_fmts('response.data', self.request.tracker_config)
            if fmts:
                self.tracker.set_response_data(
                    self.filter_tracked_data(deepcopy(self.data)),
                    formats=fmts
                )

        super().before_response()

    def apply_async(self, task_func, *args, **kwargs):
        return self.request.apply_async(task_func, *args, **kwargs)

    def delay(self, task_func, *args, **kwargs):
        return self.request.delay(task_func, *args, **kwargs)

    def get_tracked_user(self) -> dict:
        """
        to be override, user who call api
        :return:
        """

        user = self.request.user
        return {
            'username': getattr(user, 'username', None),
            'is_anonymous': getattr(user, 'is_anonymous', False)
        }

    def get_tracked_operator(self) -> dict:
        """
        to be override, user who actually make action
        :return:
        """

        return {}

    def filter_tracked_params(self, o: dict) -> dict:
        """
        to be override, remove sensitive keys from params
        :param o:
        :return:
        """
        return o

    def filter_tracked_data(self, o: dict) -> dict:
        """
        to be override, remove sensitive keys from params
        :param o:
        :return:
        """

        o.pop('data', None)
        return o
