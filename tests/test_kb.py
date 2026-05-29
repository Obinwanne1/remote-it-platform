import pytest
from app import create_app
from models import db, Article, Client


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


def test_kb_list_loads(http):
    res = http.get('/engineer/kb')
    assert res.status_code == 200


def test_create_global_article(http, app):
    res = http.post('/engineer/kb/new', data={
        'title': 'How to reset DNS',
        'body': '## Steps\n1. Open cmd\n2. `ipconfig /flushdns`',
        'category': 'Network',
        'client_id': '',
        'is_published': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        a = Article.query.filter_by(title='How to reset DNS').first()
        assert a is not None
        assert a.client_id is None
        assert a.is_global


def test_create_client_private_article(http, app):
    with app.app_context():
        client = Client(name='KB Corp', email='kb@corp.com')
        db.session.add(client)
        db.session.commit()
        client_id = client.id

    res = http.post('/engineer/kb/new', data={
        'title': 'KB Corp VPN Setup',
        'body': 'Private instructions...',
        'category': 'Network',
        'client_id': str(client_id),
        'is_published': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        a = Article.query.filter_by(title='KB Corp VPN Setup').first()
        assert a is not None
        assert a.client_id == client_id
        assert not a.is_global


def test_article_view(http, app):
    http.post('/engineer/kb/new', data={
        'title': 'View Test Article',
        'body': 'Content here',
        'category': 'General',
        'client_id': '',
        'is_published': 'on',
    })
    with app.app_context():
        a = Article.query.filter_by(title='View Test Article').first()
        article_id = a.id

    res = http.get(f'/engineer/kb/{article_id}')
    assert res.status_code == 200
    assert b'View Test Article' in res.data


def test_edit_article(http, app):
    http.post('/engineer/kb/new', data={
        'title': 'Edit Me',
        'body': 'Original',
        'category': 'General',
        'client_id': '',
        'is_published': 'on',
    })
    with app.app_context():
        a = Article.query.filter_by(title='Edit Me').first()
        article_id = a.id

    res = http.post(f'/engineer/kb/{article_id}/edit', data={
        'title': 'Edited Title',
        'body': 'Updated content',
        'category': 'Security',
        'client_id': '',
        'is_published': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        a = Article.query.get(article_id)
        assert a.title == 'Edited Title'
        assert a.category == 'Security'


def test_markdown_filter(app):
    with app.app_context():
        result = app.jinja_env.filters['markdown']('**bold** and `code`')
        assert '<strong>bold</strong>' in str(result)
        assert '<code>code</code>' in str(result)
