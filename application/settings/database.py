""" Database config

@Author Kingen
@Date 2020/5/13
"""
from sqlite3 import register_adapter, register_converter, connect, PARSE_DECLTYPES, Row

import click
from flask import g, current_app
from flask.cli import with_appcontext

from application.settings.config import logger

register_adapter(list, lambda x: '[%s]' % '_'.join(x))
register_converter('list', lambda x: [] if x.decode('utf-8') == '[]' else x.decode('utf-8').strip('[]').split('_'))


def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'], detect_types=PARSE_DECLTYPES)
        g.db.row_factory = Row
        g.db.set_trace_callback(lambda x: logger.info('Execute: %s', x))
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource('resources/video.sql') as f:
        db.executescript(f.read().decode('utf8'))


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
