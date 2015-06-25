"""
Serve the pyvo.cz website

Usage: pyvocz [options]

Options:
  --debug       Run in debug mode
  --db=URI      SQLAlchemy database URI
"""

import os

import docopt


arguments = docopt.docopt(__doc__, version='Naval Fate 2.0')
os.environ['SQLALCHEMY_DATABASE_URL'] = arguments['--db'] or 'sqlite://'

from pyvocz.app import app

if arguments['--debug']:
    app.run(debug=True)
else:
    app.run(debug=False, host='0.0.0.0')
