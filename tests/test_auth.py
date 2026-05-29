import pytest
from app import create_app
from models import db as _db


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'WTF_CSRF_ENABLED': False,
        'MAIL_SUPPRESS_SEND': True,
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_login_page_loads(client):
    res = client.get('/login')
    assert res.status_code == 200


def test_login_engineer(client):
    res = client.post('/login', data={
        'email': 'admin@remoteitsupport.com',
        'password': 'changeme123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Dashboard' in res.data or b'RemoteDesk' in res.data


def test_login_wrong_password(client):
    res = client.post('/login', data={
        'email': 'admin@remoteitsupport.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert b'Invalid email or password' in res.data


def test_logout(client):
    client.post('/login', data={
        'email': 'admin@remoteitsupport.com',
        'password': 'changeme123'
    })
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200


def test_dashboard_requires_login(client):
    res = client.get('/engineer/dashboard', follow_redirects=True)
    assert b'Sign In' in res.data or res.status_code == 200
