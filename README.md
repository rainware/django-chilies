# django-chilies
to make django more delicious

# Install
```language=bash
pip install django-chilies
```

# Example

Download examples
```language=bash
git clone https://github.com/rainware/django-chilies.git
```
```language=bash
cd django-chilies/examples
```


#### 1. setup db
```language=bash
python manage.py migrate
```

#### 2. start server
```language=bash
python manage.py runserver 0.0.0.0:8000
```

#### 3. test
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/test'
```
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/test?a=1'
```

#### 4. bookstore
* create author
```language=bash
curl --location --request POST '127.0.0.1:8000/bookstore/authors' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "zhangsan"
}'
```
```language=bash
curl --location --request POST '127.0.0.1:8000/bookstore/authors' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "lisi",
    "age": 30
}'
```
* list authors
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/authors'
```
* get author detail
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/authors/1'
```
* modify author
```language=bash
curl --location --request PUT '127.0.0.1:8000/bookstore/authors/1' \
--header 'Content-Type: application/json' \
--data-raw '{
    "age": 28
}'
```
* delete author
```language=bash
curl --location --request DELETE '127.0.0.1:8000/bookstore/authors/2'
```
* create book
```language=bash
curl --location --request POST '127.0.0.1:8000/bookstore/books' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "time",
    "author_id": 1
}'
```
* list books
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/books'
```
* get book detail
```language=bash
curl --location --request GET '127.0.0.1:8000/bookstore/books/1'
```
* modify book
```language=bash
curl --location --request PATCH '127.0.0.1:8000/bookstore/books/1' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "bookk"
}'
```
* delete book
```language=bash
curl --location --request DELETE '127.0.0.1:8000/bookstore/books/1'

```
