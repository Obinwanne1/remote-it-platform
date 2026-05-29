import pytest
from unittest.mock import patch, call
from app import create_app
from models import db, Client, User, Ticket
from cryptography.fernet import Fernet


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'MAIL_SUPPRESS_SEND': False,
        'VAULT_KEY': Fernet.generate_key(),
    })
    yield app


@pytest.fixture
def seeded(app):
    with app.app_context():
        company = Client(name='Email Corp', email='company@emailtest.com')
        db.session.add(company)
        db.session.commit()

        user = User(
            name='Client User',
            email='clientuser@emailtest.com',
            role='client_staff',
            client_id=company.id,
            is_active=True,
        )
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()

        return {'company_id': company.id}


@pytest.fixture
def eng(app, seeded):
    c = app.test_client()
    c.post('/login', data={'email': 'admin@remoteitsupport.com', 'password': 'changeme123'})
    return c


@pytest.fixture
def cli(app, seeded):
    c = app.test_client()
    c.post('/login', data={'email': 'clientuser@emailtest.com', 'password': 'pass123'})
    return c


def _first_call_kwargs(mock):
    """Return kwargs dict of first call, merging positional as (to, subject, body)."""
    args, kwargs = mock.call_args
    keys = ['to', 'subject', 'body']
    merged = dict(zip(keys, args))
    merged.update(kwargs)
    return merged


# ── new ticket notifies engineer ──────────────────────────────────────────────

def test_new_ticket_emails_engineer(app, cli, seeded):
    with patch('services.email._send') as mock_send:
        cli.post('/portal/tickets/new', data={
            'title': 'Printer broken',
            'description': 'Cannot print at all',
            'priority': 'P3',
            'category': 'Hardware',
        })
    mock_send.assert_called_once()
    kw = _first_call_kwargs(mock_send)
    assert kw['to'] == 'admin@remoteitsupport.com'
    assert 'New Ticket' in kw['subject']
    assert 'Printer broken' in kw['body']


def test_new_ticket_subject_has_ticket_number(app, cli, seeded):
    with patch('services.email._send') as mock_send:
        cli.post('/portal/tickets/new', data={
            'title': 'VPN issue',
            'description': 'Cannot connect',
            'priority': 'P2',
            'category': 'Network',
        })
    mock_send.assert_called_once()
    kw = _first_call_kwargs(mock_send)
    assert 'TKT-' in kw['subject']


def test_new_ticket_body_contains_priority(app, cli, seeded):
    with patch('services.email._send') as mock_send:
        cli.post('/portal/tickets/new', data={
            'title': 'Critical outage',
            'description': 'All systems down',
            'priority': 'P1',
            'category': 'General',
        })
    kw = _first_call_kwargs(mock_send)
    assert 'P1' in kw['body']


# ── status change notifies client ─────────────────────────────────────────────

def test_status_change_emails_client(app, eng, seeded):
    with app.app_context():
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Status test',
            description='desc',
            priority='P3',
            client_id=seeded['company_id'],
            created_by_id=engineer.id,
            status='new',
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    with patch('services.email._send') as mock_send:
        eng.post(f'/engineer/tickets/{ticket_id}/update', data={
            'status': 'in_progress',
            'priority': 'P3',
            'category': 'General',
        })
    mock_send.assert_called_once()
    kw = _first_call_kwargs(mock_send)
    assert kw['to'] == 'clientuser@emailtest.com'
    assert 'Status Updated' in kw['subject']


def test_no_email_when_status_unchanged(app, eng, seeded):
    with app.app_context():
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='No change test',
            description='desc',
            priority='P3',
            client_id=seeded['company_id'],
            created_by_id=engineer.id,
            status='new',
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    with patch('services.email._send') as mock_send:
        eng.post(f'/engineer/tickets/{ticket_id}/update', data={
            'status': 'new',
            'priority': 'P3',
            'category': 'General',
        })
    mock_send.assert_not_called()


# ── engineer comment notifies client ─────────────────────────────────────────

def test_engineer_public_comment_emails_client(app, eng, seeded):
    with app.app_context():
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Comment test',
            description='desc',
            priority='P3',
            client_id=seeded['company_id'],
            created_by_id=engineer.id,
            status='in_progress',
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    with patch('services.email._send') as mock_send:
        eng.post(f'/engineer/tickets/{ticket_id}/comment', data={
            'body': 'Investigating now.',
        })
    mock_send.assert_called_once()
    kw = _first_call_kwargs(mock_send)
    assert kw['to'] == 'clientuser@emailtest.com'
    assert 'New Reply' in kw['subject']


def test_internal_note_does_not_email_client(app, eng, seeded):
    with app.app_context():
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Internal note test',
            description='desc',
            priority='P3',
            client_id=seeded['company_id'],
            created_by_id=engineer.id,
            status='in_progress',
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    with patch('services.email._send') as mock_send:
        eng.post(f'/engineer/tickets/{ticket_id}/comment', data={
            'body': 'Internal: check the router logs.',
            'is_internal': 'on',
        })
    mock_send.assert_not_called()


# ── client reply notifies engineer ───────────────────────────────────────────

def test_client_reply_emails_engineer(app, cli, seeded):
    with app.app_context():
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Client reply test',
            description='desc',
            priority='P3',
            client_id=seeded['company_id'],
            created_by_id=engineer.id,
            status='pending_client',
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    with patch('services.email._send') as mock_send:
        cli.post(f'/portal/tickets/{ticket_id}/comment', data={
            'body': 'Still not working after the fix.',
        })
    mock_send.assert_called_once()
    kw = _first_call_kwargs(mock_send)
    assert kw['to'] == 'admin@remoteitsupport.com'
    assert 'Client Replied' in kw['subject']
