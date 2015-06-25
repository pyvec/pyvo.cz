"""
Options

Usage: pyvocz [--debug]
"""

import docopt

from pyvocz import app

arguments = docopt.docopt(__doc__, version='Naval Fate 2.0')
if arguments['--debug']:
    app.app.run(debug=True)
else:
    app.app.run(debug=False, host='0.0.0.0')
