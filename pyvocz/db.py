from flask_sqlalchemy import SQLAlchemy

from pyvodb.load import load_from_directory
from pyvodb import tables

db = SQLAlchemy()


def db_setup(datadir):
    # Workaround for https://github.com/mitsuhiko/flask-sqlalchemy/pull/250
    tables.metadata.create_all(db.engine)
    if db.session.query(tables.Event).count():
        print('Skipping DB reload')
        return
    db_reload(datadir)


def db_reload(datadir):
    for table in reversed(tables.metadata.sorted_tables):
        print('Deleting {}'.format(table))
        db.session.execute(table.delete())
    print('Loading database from {}'.format(datadir))
    load_from_directory(db.session, datadir)
    print('Database loaded')
    db.session.commit()
