import pytest
from app import create_app
from models import db, Client, User, Ticket


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'MAIL_SUPPRESS_SEND': True,
    })
    yield app


@pytest.fixture
def client_app(app):
    return app.test_client()


@pytest.fixture
def engineer_session(client_app):
    client_app.post('/login', data={
        'email': 'admin@remoteitsupport.com',
        'password': 'changeme123'
    })
    return client_app


@pytest.fixture
def sample_client(app):
    with app.app_context():
        c = Client(name='Test Corp', email='test@testcorp.com')
        db.session.add(c)
        db.session.commit()
        return c.id


def test_create_client(engineer_session, app):
    res = engineer_session.post('/engineer/clients/new', data={
        'name': 'Acme Inc',
        'email': 'contact@acme.com',
        'phone': '555-1234',
        'anydesk_id': '123456',
        'notes': 'Test client'
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        c = Client.query.filter_by(email='contact@acme.com').first()
        assert c is not None
        assert c.name == 'Acme Inc'


def test_clients_list(engineer_session):
    res = engineer_session.get('/engineer/clients')
    assert res.status_code == 200


def test_ticket_sla_set_on_create(app):
    with app.app_context():
        c = Client.query.first()
        if not c:
            c = Client(name='Corp', email='corp@corp.com')
            db.session.add(c)
            db.session.commit()

        engineer = User.query.filter_by(role='engineer').first()
        t = Ticket(
            title='Test ticket',
            description='Test desc',
            priority='P2',
            client_id=c.id,
            created_by_id=engineer.id
        )
        t.set_sla()
        assert t.sla_deadline is not None
        # P2 = 4 hour SLA
        from datetime import datetime
        delta = t.sla_deadline - datetime.utcnow()
        assert 3.9 < delta.total_seconds() / 3600 < 4.1


def test_ticket_number_format(app):
    with app.app_context():
        c = Client.query.first()
        if not c:
            c = Client(name='Corp', email='corp2@corp.com')
            db.session.add(c)
            db.session.commit()

        engineer = User.query.filter_by(role='engineer').first()
        t = Ticket(
            title='Num test',
            description='Desc',
            priority='P3',
            client_id=c.id,
            created_by_id=engineer.id
        )
        db.session.add(t)
        db.session.commit()
        assert t.ticket_number.startswith('TKT-')
