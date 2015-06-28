import tempfile
import shutil
import os

import pytest
import pytest_flask as pt_flask

from pyvocz.app import create_app, DEFAULT_DATA_DIR

def pytest_addoption(parser):
    parser.addoption("--check-external-links", action="store_true",
        help="Check external links when running the tests.")
    parser.addoption("--all-data", action="store_true",
        help="Load all the meetup data, not just a testing subset.")


@pytest.fixture
def check_external_links(pytestconfig):
    return pytestconfig.getoption('check_external_links')


@pytest.yield_fixture
def app(pytestconfig):
    src = DEFAULT_DATA_DIR
    if pytestconfig.getoption('all_data'):
        yield create_app(db_uri='sqlite://', datadir=src, echo=False)
    else:
        with tempfile.TemporaryDirectory() as tempdir:
            for name in """
                    ostrava/2014-08-07.yaml
                    ostrava/2014-10-02-balis-balim-balime.yaml
                    ostrava/2014-11-06-testovaci.yaml
                    ostrava/2013-11-07-prvni.yaml
                    ostrava/2013-12-04-druhe.yaml
                    brno/2014-07-31-bitva-tri-cisaru.yaml
                    brno/2013-05-30-gui.yaml
                    brno/2015-02-26-dokumentacni.yaml
                    brno/2014-02-27-vyjezdove.yaml
                    praha/2015-05-20-anniversary.yaml
                    praha/2015-03-18-zase-docker.yaml
                    praha/2011-01-17.yaml
                    praha/2015-04-15.yaml
                    """.splitlines():
                name = name.strip()
                if name:
                    try:
                        os.mkdir(os.path.dirname(os.path.join(tempdir, name)))
                    except FileExistsError:
                        pass
                    shutil.copyfile(
                        os.path.join(src, name),
                        os.path.join(tempdir, name),
                    )
            yield create_app(db_uri='sqlite://', datadir=tempdir, echo=False)
