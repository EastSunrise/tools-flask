""" Development config

@Author Kingen
@Date 2020/5/12
"""
from . import Config


class DevelopmentConfig(Config):
    SQL_ALCHEMY_ECHO = True
    FLASK_ENV = 'development'
    FLASK_DEBUG = 1
