import setuptools

setuptools.setup(
    name="django-chilies",
    version="0.0.2-alpha-1",
    author="rainware",
    author_email="kevin90116@gmail.com",
    description="to make django more delicious",
    url="https://github.com/rainware/django-chilies",
    project_urls={
        "Source": "https://github.com/rainware/django-chilies",
    },
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8.5',
    install_requires=[
        'django>=4.2',
        'djangorestframework>=3.14.0',
        'celery>=4.4.0',
        'kafka-python>=2.0.2',
        'pytz>=2020.1'
    ],
    platforms='any'
)
