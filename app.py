from flask import Flask

from config import Config
from routes import register_routes
from routes.reconocimiento import start_camera_threads


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["UPLOAD_FOLDER"] = "static/fotos"

    register_routes(app)

    with app.app_context():
        start_camera_threads()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
