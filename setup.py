import os
from setuptools import find_packages, setup
from carrot import __version__


def readme():
    with open('README.rst') as f:
        return f.read()


os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

if os.environ.get('TRAVIS_BRANCH') == 'develop':
    name = 'django-carrot-dev'
    version = os.environ.get('TRAVIS_BUILD_NUMBER')

else:
    name = 'django-carrot'
    version = __version__


setup(
    name=name,
    version=version,
    packages=find_packages(),
    include_package_data=True,
    license='Apache Software License',
    description='A RabbitMQ asynchronous task queue for Django.',
    long_description=readme(),
    author='Christopher Davies',
    author_email='christopherdavies553@gmail.com',
    url='https://django-carrot.readthedocs.io',
    home_page='https://github.com/chris104957/django-carrot',
    project_urls={
        'Documentation': 'https://django-carrot.readthedocs.io',
        'Source': 'https://github.com/chris104957/django-carrot',
    },

    classifiers=[
        'Environment :: Web Environment',
        'Development Status :: 5 - Production/Stable',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    install_requires=['json2html>=1.3.0', 'pika>=0.10.0', 'djangorestframework>=3.6', 'psutil>=5.4.5']
)

