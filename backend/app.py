"""Web application entry point. Run from the repository root: python backend/app.py"""
import os
import secrets
import sys

from flask import Flask

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.routes import web
from backend.service import TransportService


def create_app():
    app = Flask(__name__, template_folder=os.path.join(ROOT, "frontend", "templates"),
                static_folder=os.path.join(ROOT, "frontend", "static"))
    app.config["SECRET_KEY"] = os.environ.get("TRANSPORT_SECRET") or secrets.token_hex(32)
    app.config["TRANSPORT_SERVICE"] = TransportService(os.path.join(ROOT, "transport_data.json"))
    app.register_blueprint(web)
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
