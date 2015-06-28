from flask.ext.sqlalchemy import SQLAlchemy

from pyvodb.load import get_db
from pyvodb import tables

db = SQLAlchemy()

def db_setup(app, datadir):
    # Workaround for https://github.com/mitsuhiko/flask-sqlalchemy/pull/250
    tables.metadata.create_all(db.engine)
    if db.session.query(tables.Event).count():
        print('Skipping DB reload')
        return
    print('Loading database from {}'.format(datadir))
    get_db(datadir, engine=db.engine)
    print('Database loaded')
