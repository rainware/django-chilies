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
curl --location --request GET '127.0.0.1:8000/bookstore/test?a=1'
```

#### 4. bookstore
```language=bash
# create author
curl --location --request POST '127.0.0.1:8000/bookstore/authors' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "zhangsan"
}'

curl --location --request POST '127.0.0.1:8000/bookstore/authors' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "lisi",
    "age": 30
}'

# list authors
curl --location --request GET '127.0.0.1:8000/bookstore/authors'

# get author detail
curl --location --request GET '127.0.0.1:8000/bookstore/authors/1'

# modify author
curl --location --request PUT '127.0.0.1:8000/bookstore/authors/1' \
--header 'Content-Type: application/json' \
--data-raw '{
    "age": 28
}'

# delete author
curl --location --request DELETE '127.0.0.1:8000/bookstore/authors/2'

# create book
curl --location --request POST '127.0.0.1:8000/bookstore/books' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "time",
    "author_id": 1
}'

# list books
curl --location --request GET '127.0.0.1:8000/bookstore/books'

# get book detail
curl --location --request GET '127.0.0.1:8000/bookstore/books/1'

# modify book
curl --location --request PATCH '127.0.0.1:8000/bookstore/books/1' \
--header 'Content-Type: application/json' \
--data-raw '{
    "name": "bookk"
}'

# delete book
curl --location --request DELETE '127.0.0.1:8000/bookstore/books/1'

```
