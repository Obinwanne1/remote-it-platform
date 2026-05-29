import pytest
from datetime import datetime
from app import create_app
from models import db, Client, Ticket, RemoteSession
from cryptography.fernet import Fernet


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'MAIL_SUPPRESS_SEND': True,
        'VAULT_KEY': Fernet.generate_key(),
    })
    yield app


@pytest.fixture
def http(app):
    c = app.test_client()
    c.post('/login', data={'email': 'admin@remoteitsupport.com', 'password': 'changeme123'})
    return c


@pytest.fixture
def sample_client(app):
    with app.app_context():
        client = Client(name='Report Corp', email='report@corp.com')
        db.session.add(client)
        db.session.commit()
        return client.id


def test_report_form_loads(http, sample_client):
    res = http.get(f'/engineer/clients/{sample_client}/report')
    assert res.status_code == 200
    assert b'Generate Report' in res.data


def test_report_pdf_content_type(http, app, sample_client):
    now = datetime.utcnow()
    res = http.get(f'/engineer/clients/{sample_client}/report/pdf?month={now.month}&year={now.year}')
    assert res.status_code == 200
    assert res.content_type == 'application/pdf'


def test_report_pdf_has_content(http, app, sample_client):
    now = datetime.utcnow()
    res = http.get(f'/engineer/clients/{sample_client}/report/pdf?month={now.month}&year={now.year}')
    # PDF magic bytes
    assert res.data[:4] == b'%PDF'


def test_report_pdf_with_tickets(http, app, sample_client):
    with app.app_context():
        from models import User
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Report ticket',
            description='desc',
            priority='P2',
            client_id=sample_client,
            created_by_id=engineer.id,
            status='resolved',
            resolved_at=datetime.utcnow(),
        )
        ticket.set_sla()
        db.session.add(ticket)

        session = RemoteSession(
            ticket_id=ticket.id if ticket.id else 1,
            client_id=sample_client,
            engineer_id=engineer.id,
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            duration_minutes=45,
            notes='Fixed issue',
        )
        # Need to flush ticket first to get its id
        db.session.flush()
        session.ticket_id = ticket.id
        db.session.add(session)
        db.session.commit()

    now = datetime.utcnow()
    res = http.get(f'/engineer/clients/{sample_client}/report/pdf?month={now.month}&year={now.year}')
    assert res.status_code == 200
    assert res.data[:4] == b'%PDF'


def test_report_pdf_invalid_month(http, sample_client):
    res = http.get(f'/engineer/clients/{sample_client}/report/pdf?month=abc&year=2026')
    assert res.status_code == 400
