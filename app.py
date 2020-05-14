""" Application startup

@Author Kingen
@Date 2020/5/12
"""

from flask import Flask, g

from application.apps.video import video_blu
from application.settings.dev import DevelopmentConfig
from application.settings.prop import ProductionConfig

app = Flask(__name__)

dev_config = DevelopmentConfig
prop_config = ProductionConfig
app.config.from_object(dev_config)


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


app.register_blueprint(video_blu, url_prefix='/video')

if __name__ == '__main__':
    app.run()
