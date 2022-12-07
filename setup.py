import setuptools

setuptools.setup(
    name="django-chilies",
    version="0.0.1-alpha-1",
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
        'django>=3.1',
        'djangorestframework>=3.11.1',
        'celery>=5.2.1',
        'kafka-python>=2.0.2',
        'pytz==2021.3',
        'django-composite-foreignkey==1.1.0',
    ],
    platforms='any'
)
