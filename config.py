import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()


def _get_vault_key():
    key = os.environ.get('VAULT_KEY')
    if not key:
        key = Fernet.generate_key().decode()
        print(f"[WARNING] VAULT_KEY not set. Generated ephemeral key: {key}")
        print("[WARNING] Credentials encrypted with this key will be lost on restart. Set VAULT_KEY in .env")
    return key.encode() if isinstance(key, str) else key


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    VAULT_KEY = _get_vault_key()
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///remote_it.db')
    # Railway/Heroku legacy URIs use postgres:// — SQLAlchemy 2.x requires postgresql://
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@remoteitsupport.com')
    MAIL_SUPPRESS_SEND = os.environ.get('FLASK_ENV') == 'development' and not os.environ.get('MAIL_USERNAME')

    SLA_HOURS = {'P1': 1, 'P2': 4, 'P3': 24, 'P4': 72}

    # Default engineer credentials (change on first login)
    DEFAULT_ENGINEER_EMAIL = os.environ.get('ENGINEER_EMAIL', 'admin@remoteitsupport.com')
    DEFAULT_ENGINEER_PASSWORD = os.environ.get('ENGINEER_PASSWORD', 'changeme123')
    DEFAULT_ENGINEER_NAME = os.environ.get('ENGINEER_NAME', 'IT Engineer')
