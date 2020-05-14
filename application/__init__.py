""" Application Initialize

@Author Kingen
@Date 2020/5/12
"""
import os

from flask import Flask

from application.settings.config import DevelopmentConfig


def create_app(config=DevelopmentConfig):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'tools.db'),
    )
    app.config.from_object(config)

    @app.route('/hello')
    def hello():
        return 'Hello!'

    from application.settings import database
    database.init_app(app)

    from application.video import video_blu
    app.register_blueprint(video_blu, url_prefix='/video')

    return app
