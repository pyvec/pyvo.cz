import tempfile
import shutil
import os

import pytest

from pyvocz.app import create_app, DEFAULT_DATA_DIR


def pytest_addoption(parser):
    parser.addoption(
        "--check-external-links", action="store_true",
        help="Check external links when running the tests.")
    parser.addoption(
        "--all-data", action="store_true",
        help="Load all the meetup data, not just a testing subset.")


@pytest.fixture
def check_external_links(pytestconfig):
    return pytestconfig.getoption('check_external_links')


@pytest.fixture
def app(pytestconfig):
    src = DEFAULT_DATA_DIR
    if pytestconfig.getoption('all_data'):
        yield create_app(datadir=src, echo=False)
    else:
        with tempfile.TemporaryDirectory() as tempdir:
            for name in """
                    meta.yaml
                    series/ostrava-pyvo/series.yaml
                    series/ostrava-pyvo/events/2014-08-07.yaml
                    series/ostrava-pyvo/events/2014-10-02-balis-balim-balime.yaml
                    series/ostrava-pyvo/events/2014-11-06-testovaci.yaml
                    series/ostrava-pyvo/events/2013-11-07-prvni.yaml
                    series/ostrava-pyvo/events/2013-12-04-druhe.yaml
                    series/brno-pyvo/series.yaml
                    series/brno-pyvo/events/2014-07-31-bitva-tri-cisaru.yaml
                    series/brno-pyvo/events/2013-05-30-gui.yaml
                    series/brno-pyvo/events/2015-02-26-dokumentacni.yaml
                    series/brno-pyvo/events/2014-02-27-vyjezdove.yaml
                    series/brno-pyvo/events/2012-11-29-cli.yaml
                    series/praha-pyvo/series.yaml
                    series/praha-pyvo/events/2015-05-20-anniversary.yaml
                    series/praha-pyvo/events/2015-03-18-zase-docker.yaml
                    series/praha-pyvo/events/2011-01-17.yaml
                    series/praha-pyvo/events/2015-04-15.yaml
                    cities/brno/city.yaml
                    cities/brno/venues/u-dreveneho-orla.yaml
                    cities/brno/venues/u-drevaka.yaml
                    cities/brno/venues/hlavni-nadrazi.yaml
                    cities/praha/city.yaml
                    cities/praha/venues/konvikt.yaml
                    cities/praha/venues/na-venecku.yaml
                    cities/ostrava/city.yaml
                    cities/ostrava/venues/ires-sc.yaml
                    cities/ostrava/venues/sport-club.yaml
                    cities/ostrava/venues/vr-levsky.yaml
                    """.splitlines():
                name = name.strip()
                if name:
                    try:
                        os.makedirs(os.path.dirname(os.path.join(tempdir,
                                                                 name)))
                    except FileExistsError:
                        pass
                    shutil.copyfile(
                        os.path.join(src, name),
                        os.path.join(tempdir, name),
                    )
            yield create_app(datadir=tempdir, echo=False)
