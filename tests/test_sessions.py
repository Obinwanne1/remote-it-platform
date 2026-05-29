import pytest
from app import create_app
from models import db, Client, Ticket, RemoteSession


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
def http(app):
    c = app.test_client()
    c.post('/login', data={'email': 'admin@remoteitsupport.com', 'password': 'changeme123'})
    return c


@pytest.fixture
def sample_ticket(app):
    with app.app_context():
        client = Client(name='Session Corp', email='session@corp.com')
        db.session.add(client)
        db.session.commit()
        from models import User
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket(
            title='Session test', description='desc', priority='P2',
            client_id=client.id, created_by_id=engineer.id
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()
        return ticket.id


def test_start_session(http, app, sample_ticket):
    res = http.post(f'/engineer/tickets/{sample_ticket}/session/start', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        s = RemoteSession.query.filter_by(ticket_id=sample_ticket).first()
        assert s is not None
        assert s.is_active


def test_end_session(http, app, sample_ticket):
    http.post(f'/engineer/tickets/{sample_ticket}/session/start')
    with app.app_context():
        s = RemoteSession.query.filter_by(ticket_id=sample_ticket).first()
        session_id = s.id

    res = http.post(f'/engineer/sessions/{session_id}/end',
                    data={'notes': 'Resolved network issue'},
                    follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        s = RemoteSession.query.get(session_id)
        assert s.ended_at is not None
        assert s.duration_minutes >= 1
        assert s.notes == 'Resolved network issue'


def test_session_duration_label(app, sample_ticket):
    with app.app_context():
        from models import User
        engineer = User.query.filter_by(role='engineer').first()
        ticket = Ticket.query.get(sample_ticket)

        for mins, expected in [(90, '1h 30m'), (45, '45m'), (0, '0m')]:
            s = RemoteSession(
                ticket_id=sample_ticket,
                client_id=ticket.client_id,
                engineer_id=engineer.id,
                duration_minutes=mins
            )
            db.session.add(s)
            db.session.flush()
            assert s.duration_label == expected
            db.session.rollback()

        s_active = RemoteSession(
            ticket_id=sample_ticket,
            client_id=ticket.client_id,
            engineer_id=engineer.id,
            duration_minutes=None
        )
        db.session.add(s_active)
        db.session.flush()
        assert s_active.duration_label == 'Active'
        db.session.rollback()


def test_double_start_ends_previous(http, app, sample_ticket):
    http.post(f'/engineer/tickets/{sample_ticket}/session/start')
    http.post(f'/engineer/tickets/{sample_ticket}/session/start')
    with app.app_context():
        sessions = RemoteSession.query.filter_by(ticket_id=sample_ticket).all()
        assert len(sessions) == 2
        completed = [s for s in sessions if not s.is_active]
        assert len(completed) == 1
