""" Init config of Flask

@Author Kingen
@Date 2020/5/14
"""
import importlib
import logging.config
import os
from sqlite3 import connect, Row, PARSE_DECLTYPES, register_adapter, register_converter

import click
import yaml
from flask import current_app, g
from flask.cli import with_appcontext
from jinja2.tests import test_undefined

from tools.utils.common import BaseEnum


def init_app(app):
    init_logging(app)
    init_sqlite()
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    con = connect(app.config['DATABASE'])
    con.close()

    @app.template_test('blank')
    def test_blank(s):
        return test_undefined(s) or s is None or s == ''

    @app.route('/')
    def hello():
        return 'Hello!'


# config for logging
def init_logging(app):
    if not os.path.exists('logs'):
        os.mkdir('logs')
    with app.open_resource('resources/logging.yml', 'r') as fp:
        config = yaml.load(fp.read(), Loader=yaml.Loader)
    logging.config.dictConfig(config)


def init_sqlite():
    register_adapter(list, lambda x: '[%s]' % '_'.join(x))
    register_converter(list.__name__, lambda x: [] if x.decode('utf-8') == '[]' else x.decode('utf-8').strip('[]').split('_'))
    importlib.import_module('tools.video.enums')
    for subclass in BaseEnum.__subclasses__():
        register_adapter(subclass, lambda x: None if x is None else x.to_code())
        register_converter(subclass.__name__, list(subclass.__members__.values())[0].from_code)


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


def init_db():
    db = get_db()
    with current_app.open_resource('resources/tools.sql') as f:
        db.executescript(f.read().decode('utf8'))


logger = logging.getLogger(__name__)


def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'], detect_types=PARSE_DECLTYPES)
        g.db.row_factory = Row
        g.db.set_trace_callback(lambda x: logger.info('Execute: %s', x))
    return g.db


def is_blank(s):
    return s[::-1]
