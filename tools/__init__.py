""" Application Initialize

@Author Kingen
@Date 2020/5/12
"""
import logging.config
import os

import yaml
from flask import Flask


def create_app(config_file, db):
    """
    :param config_file: relative path to root_path
    :return:
    """
    # app config
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, db),
    )
    app.config.from_pyfile(config_file)

    # config for logging
    if not os.path.exists('logs'):
        os.mkdir('logs')
    with open(r'tools/resources/logging.yml', 'r') as file:
        config = yaml.load(file.read(), Loader=yaml.Loader)
    logging.config.dictConfig(config)

    @app.route('/hello')
    def hello():
        return 'Hello!'

    from tools.settings import database
    database.init_app(app)

    from tools import video
    app.register_blueprint(video.video_blu, url_prefix='/video')

    return app
