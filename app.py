import os
import markdown as md
from markupsafe import Markup
from flask import Flask, redirect, url_for
from config import Config
from models import db, User
from services.email import mail
from routes.auth import auth_bp
from routes.engineer import engineer_bp
from routes.client import client_bp
from routes.kb import kb_bp


def create_app(config=None):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)

    if config:
        app.config.update(config)

    db.init_app(app)
    mail.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(engineer_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(kb_bp)

    @app.template_filter('markdown')
    def markdown_filter(text):
        return Markup(md.markdown(text or '', extensions=['fenced_code', 'tables', 'nl2br']))

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()
        _seed_engineer(app)

    return app


def _seed_engineer(app):
    """Create default engineer account if none exists."""
    engineer = User.query.filter_by(role='engineer').first()
    if not engineer:
        engineer = User(
            email=app.config['DEFAULT_ENGINEER_EMAIL'],
            name=app.config['DEFAULT_ENGINEER_NAME'],
            role='engineer'
        )
        engineer.set_password(app.config['DEFAULT_ENGINEER_PASSWORD'])
        db.session.add(engineer)
        db.session.commit()
        print(f"[INIT] Engineer account created: {engineer.email} / {app.config['DEFAULT_ENGINEER_PASSWORD']}")
        print("[INIT] Change this password immediately.")


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
