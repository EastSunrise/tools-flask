""" Database config

@Author Kingen
@Date 2020/5/13
"""
from sqlite3 import register_adapter, register_converter, connect, PARSE_DECLTYPES, Row

from flask import g

from . import logger

register_adapter(list, lambda x: '[%s]' % '_'.join(x))
register_converter('list', lambda x: [] if x.decode('utf-8') == '[]' else x.decode('utf-8').strip('[]').split('_'))

DATABASE = '/application/db/tools.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect(DATABASE, 30, detect_types=PARSE_DECLTYPES)
        db.row_factory = Row
        db.set_trace_callback(lambda x: logger.info('Execute: %s', x))
    return db
