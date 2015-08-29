"""
Serve the pyvo.cz website

Usage: pyvocz [options]

Options:
  --debug       Run in debug mode
  --db=URI      SQLAlchemy database URI
  --data=DIR    Data directory
  --pull-password=PWD
                Password for Git pull webhook
"""

import os

import docopt

from pyvocz.app import create_app, DEFAULT_DATA_DIR


arguments = docopt.docopt(__doc__)


db_uri = arguments['--db'] or 'sqlite://'
datadir = arguments['--data'] or DEFAULT_DATA_DIR
pull_password = arguments['--pull-password']
app = create_app(db_uri=db_uri, datadir=datadir, pull_password=pull_password)

if arguments['--debug']:
    app.run(debug=True)
else:
    app.run(debug=False, host='0.0.0.0')
