"""
Serve the pyvo.cz website

Usage: pyvocz [options]

Options:
  --debug       Run in debug mode
  --db=URI      SQLAlchemy database URI
  --data=DIR    Data directory
  --host=HOST   Host to serve on (enables subdomain redirects)
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
port = int(arguments['--port'] or 5000)
host = arguments['--host']

app = create_app(db_uri=db_uri, datadir=datadir, pull_password=pull_password,
                 host=host, port=port)

if not os.path.exists(datadir):
    subprocess.check_call(['git', 'clone',
                           'https://github.com/pyvec/pyvo-data', datadir])

if arguments['--debug']:
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    # Workaround for https://github.com/pallets/flask/issues/1907
    app.jinja_env.auto_reload = True
    app.run(debug=True, host=host, port=port)
else:
    app.run(debug=False, host=host or '0.0.0.0', port=port)
