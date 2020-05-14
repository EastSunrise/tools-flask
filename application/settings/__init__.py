""" Global config

@Author Kingen
@Date 2020/5/12
"""
import logging.config
import os

import yaml


class Config:
    DEBUG = False

    LOG_LEVEL = "INFO"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_POOL_SIZE = 10
    SQLALCHEMY_POOL_TIMEOUT = 10
    SQLALCHEMY_MAX_OVERFLOW = 2

    if not os.path.exists('logs'):
        os.mkdir('logs')
    with open(os.path.join(os.path.dirname(__file__), 'logging.yml'), 'r') as file:
        config = yaml.load(file.read(), Loader=yaml.Loader)
    logging.config.dictConfig(config)


def get_logger(name='default'):
    """
    Get a common logger named by the module name.
    :param name: module name
    :return:
    """
    return logging.getLogger(name)


logger = get_logger(__name__)
