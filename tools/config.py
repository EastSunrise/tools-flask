""" Config file

@Author Kingen
@Date 2020/5/14
"""
import logging.config
import os

import yaml


# config for logging
def init_logging(app):
    if not os.path.exists('logs'):
        os.mkdir('logs')
    with app.open_resource('resources/logging.yml', 'r') as fp:
        config = yaml.load(fp.read(), Loader=yaml.Loader)
    logging.config.dictConfig(config)
