from django.db import models

# Create your models here.
from django_chilies.models import ModelWrapper


class Author(ModelWrapper):
    sensitive_fields = ['age']

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=32)
    age = models.IntegerField(null=True)

    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)


class Book(ModelWrapper):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=64)
    author = models.ForeignKey(Author, related_name='books', null=True,
                               on_delete=models.PROTECT, db_constraint=False)

    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
