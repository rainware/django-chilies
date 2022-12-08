from .test_controller import TestController
from .author.create import CreateAuthorController
from .author.list import ListAuthorsController

from .author.modify import ModifyAuthorController
from .author.detail import GetAuthorDetailController
from .author.delete import DeleteAuthorController
from .book.create import CreateBookController
from .book.list import ListBooksController
from .book.modify import ModifyBookController
from .book.detail import GetBookDetailController
from .book.delete import DeleteBookController

__all__ = ('TestController', 'CreateAuthorController', 'ListAuthorsController',
           'ModifyAuthorController', 'GetAuthorDetailController', 'DeleteAuthorController',
           'CreateBookController', 'ListBooksController',
           'ModifyBookController', 'GetBookDetailController', 'DeleteBookController',
           )
