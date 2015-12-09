"""
Serve the pyvo.cz website

Usage: pyvocz [options]

Options:
  --debug       Run in debug mode
  --db=URI      SQLAlchemy database URI
  --data=DIR    Data directory
  --port=PORT   Port to serve on
  --pull-password=PWD
                Password for Git pull webhook

If the data directory does not exists, clones a default repo into it.
"""

import os
import subprocess

import docopt

from pyvocz.app import create_app, DEFAULT_DATA_DIR


arguments = docopt.docopt(__doc__)


db_uri = arguments['--db'] or 'sqlite://'
datadir = arguments['--data'] or DEFAULT_DATA_DIR
pull_password = arguments['--pull-password']
app = create_app(db_uri=db_uri, datadir=datadir, pull_password=pull_password)

if not os.path.exists(datadir):
    subprocess.check_call(['git', 'clone',
                           'https://github.com/pyvec/pyvo-data', datadir])

port = int(arguments.get('--port', 5000))

if arguments['--debug']:
    app.run(debug=True, port=port)
else:
    app.run(debug=False, host='0.0.0.0', port=port)
