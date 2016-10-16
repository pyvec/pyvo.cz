
import os
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

tests_require = ['pytest', 'pytest-flask', 'lxml', 'requests', 'cssselect']

def data_file_names():
    for top in 'pyvocz/static', 'pyvocz/templates':
        for dirname, dirs, files in os.walk(top):
            for filename in files:
                fullname = os.path.join(dirname, filename)
                if filename not in dirs and fullname.endswith((
                        '.png', '.svg', '.jpg', '.css', '.html',
                        )):
                    yield os.path.relpath(fullname, 'pyvocz')

setup_args = dict(
    name='pyvocz',
    version='0.2',
    packages=['pyvocz'],

    description="""Website with information about Pyvo meetups (pyvo.cz)""",
    author='Petr Viktorin',
    author_email='encukou@gmail.com',
    url='https://github.com/pyvec/pyvo.cz',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],

    install_requires=[
        'pyvodb >= 0.3, < 0.4',
        'flask >= 0.10, < 1.0',
        'flask-sqlalchemy >= 2.0, <3.0',
        'docopt >= 0.6, < 1.0',
        'ics >= 0.3.1, < 1.0',
        'feedgen >= 0.3.1, < 1.0',
        'markdown >= 2.6.7, < 3.0',
    ],

    package_data={'pyvocz': list(data_file_names())},

    extras_require={
        'test': tests_require,
    },

    tests_require=tests_require,
    cmdclass={'test': PyTest},
)


if __name__ == '__main__':
    setup(**setup_args)
