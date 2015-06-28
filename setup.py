
import sys

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):
    def finalize_options(self):
        super().finalize_options()
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


setup_args = dict(
    name='pyvocz',
    version='0.0.1',
    packages=['pyvocz'],

    description="""Website with information about Pyvo meetups (pyvo.cz)""",
    author='Petr Viktorin',
    author_email='encukou@gmail.com',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
    ],

    install_requires=[
        'pyvodb',
        'flask >= 0.10, < 1.0',
        'flask-sqlalchemy >= 2.0, <3.0',
        'docopt >= 0.6, < 1.0',
        'czech-holidays',
        'ics >= 0.3.1, < 1.0',
        'feedgen >= 0.3.1, < 1.0',
    ],

    tests_require=['pytest', 'pytest-flask'],
    cmdclass={'test': PyTest},
)


if __name__ == '__main__':
    setup(**setup_args)
