from django.urls import path
from .controllers import *

app_name = 'bookstore'
urlpatterns = [
    path('test', TestController.as_view(), name='test'),
    path('authors', CreateAuthorController.with_siblings(ListAuthorsController).as_view(), name='author-list'),
    path('authors/<int:author_id>', GetAuthorDetailController.with_siblings(ModifyAuthorController, DeleteAuthorController).as_view(), name='author-detail'),
    path('books', CreateBookController.with_siblings(ListBooksController).as_view(), name='book-list'),
    path('books/<int:book_id>', GetBookDetailController.with_siblings(ModifyBookController, DeleteBookController).as_view(), name='book-detail'),
]
