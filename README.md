# The pyvo.cz website

This is the code that runs pyvo.cz, the directory of Czech Python meetups.
You're welcome to help with development.

# Installation

To install, create and activate a virtualenv:

    python3 -m venv pyvocz-env
    . pyvocz-env/bin/activate
    pip install -U pip wheel

Then install with:

    pip install -e git+https://github.com/pyvec/pyvo.cz#egg=pyvocz

Alternatively, if you've cloned the repository, run this in your copy:

    pip install -e.

(Nothing should depend on the pyvocz module, so it's not on PyPI.)

# Running

Then, run with:

    python -m pyvocz --debug

Note that this will pull the data from https://github.com/pyvec/pyvo-data on
first run. For other options, see `python -m pyvocz --help`.

For deployment configuration, see `app.py`.

# Testing

To test, you'll need some additional dependencies.
From the source directory, do:

    pip install -e.[test]

Then, you can test with:

    python -m pytest test_pyvocz/
