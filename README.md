# The pyvo.cz website

To install, create and activate a virtualenv:

    python3 -m venv pyvocz-env
    . pyvocz-env/bin/activate
    pip install -U pip wheel

Then install with:

    pip install -e git+https://github.com/pyvec/pyvo.cz#egg=pyvocz

(Nothing should depend on this, so it's not on PyPI.)

Then, run with:

    python -m pyvocz --debug

Note that this will pull the data from https://github.com/pyvec/pyvo-data on
first run. For other options, see `python -m pyvocz --help`.

For deployment configuration, see `app.py`.
