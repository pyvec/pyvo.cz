"""
Configuration for deploying pyvo.cz on the rosti.cz hosting.

It should be easy to adapt to other kinds of WSGI-based hosting.


Instructions:
- Put this repo in /srv/app. You'll need to clear the previous contents:

        rm -rf /srv/app
        git clone https://github.com/pyvec/pyvo.cz /srv/app

- Clone the data directory here:

        git clone https://github.com/pyvec/pyvo-data /srv/app/pyvo-data

- Make a password file for the Github hook:

        echo YOUR_RANDOM_PASSWORD > pull_password

  (This is not too secure; it's just to avoid DoS from anyone having access
  to the DB reload functionality)

- Install everything:

        pip install -r requirements.txt

- Deploy:

        supervisorctl restart app

- Configure the Github hook for pyvec/pyvo-data to
  POST to pyvo.cz/api/reload_hook?password=YOUR_RANDOM_PASSWORD

"""

import logging

from pyvocz.app import create_app


logging.basicConfig(level=logging.INFO)

db = 'sqlite:////srv/app/db.sqlite'
datadir = 'pyvo-data'

try:
    password_file = open('pull_password')
except FileNotFoundError:
    pull_password = None
else:
    with password_file:
        pull_password = password_file.read().strip()


application = create_app(db, datadir=datadir, echo=False, pull_password=pull_password)
