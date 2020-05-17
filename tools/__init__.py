""" Application Initialize

@Author Kingen
@Date 2020/5/12
"""
import os

from flask import Flask


def create_app(config_file, db):
    """
    :param config_file: relative path to instance_path
    :return:
    """
    # app config
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, db),
    )
    app.config.from_pyfile(os.path.join(app.instance_path, config_file))

    from tools.config import init_logging, init_app
    init_app(app)

    from tools import video
    app.register_blueprint(video.video_blu, url_prefix='/video')

    return app
