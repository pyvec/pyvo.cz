import os
import datetime

from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload
from flask import Flask
from flask import render_template
from flask.ext.sqlalchemy import SQLAlchemy
from jinja2.exceptions import TemplateNotFound

from pyvodb.load import get_db
from pyvodb import tables

app = Flask(__name__)
app.config.setdefault('SQLALCHEMY_DATABASE_URI', os.environ['SQLALCHEMY_DATABASE_URI'])
app.config.setdefault('SQLALCHEMY_ECHO', True)
db = SQLAlchemy(app)

@app.before_first_request
def setup():
    # Workaround for https://github.com/mitsuhiko/flask-sqlalchemy/pull/250
    datadir = app.config.get('PYVOCZ_DATA_PATH',
                             os.path.join(app.root_path, 'data'))
    tables.metadata.create_all(db.engine)
    if db.session.query(tables.Event).count():
        print('Skipping DB reload')
        return
    print('Loading database from {}'.format(datadir))
    get_db(datadir, engine=db.engine)
    print('Database loaded')

@app.route('/')
def index():
    today = datetime.date.today()

    subquery = db.session.query(
        tables.Event.city_id,
        func.max(tables.Event.date).label('latest_date')
    )
    subquery = subquery.group_by(tables.Event.city_id)
    subquery = subquery.subquery()

    query = db.session.query(tables.Event)
    query = query.join(subquery,
                       and_(subquery.c.latest_date == tables.Event.date,
                            subquery.c.city_id == tables.Event.city_id,
                            ))
    # order: upcoming first, then by distance from today
    query = query.order_by(subquery.c.latest_date < today,
                           func.abs(subquery.c.latest_date - today))
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    latest_events = query.all()

    return render_template('index.html', latest_events=latest_events, today=today)

@app.route('/<cityslug>')
def city(cityslug):
    query = db.session.query(tables.City)
    query = query.filter(tables.City.slug == cityslug)
    city = query.one()

    try:
        return render_template('cities/{}.html'.format(cityslug), city=city)
    except TemplateNotFound:
        return render_template('city.html', city=city)
