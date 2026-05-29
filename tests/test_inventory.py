import pytest
from app import create_app
from models import db, Client, Device, Credential
from cryptography.fernet import Fernet


TEST_VAULT_KEY = Fernet.generate_key()


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'MAIL_SUPPRESS_SEND': True,
        'VAULT_KEY': TEST_VAULT_KEY,
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
        client = Client(name='Inventory Corp', email='inv@corp.com')
        db.session.add(client)
        db.session.commit()
        return client.id


def test_add_device(http, app, sample_client):
    res = http.post(f'/engineer/clients/{sample_client}/devices/new', data={
        'hostname': 'ROUTER-01',
        'ip_address': '192.168.1.1',
        'device_type': 'router',
        'os': 'RouterOS 7.1',
        'mac_address': 'AA:BB:CC:DD:EE:FF',
        'notes': 'Main gateway',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        d = Device.query.filter_by(hostname='ROUTER-01').first()
        assert d is not None
        assert d.ip_address == '192.168.1.1'
        assert d.device_type == 'router'
        assert d.is_active


def test_edit_device(http, app, sample_client):
    http.post(f'/engineer/clients/{sample_client}/devices/new', data={
        'hostname': 'SW-01', 'device_type': 'switch',
    })
    with app.app_context():
        d = Device.query.filter_by(hostname='SW-01').first()
        device_id = d.id

    res = http.post(f'/engineer/clients/{sample_client}/devices/{device_id}/edit', data={
        'hostname': 'SW-01-UPDATED',
        'ip_address': '10.0.0.2',
        'device_type': 'switch',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        d = Device.query.get(device_id)
        assert d.hostname == 'SW-01-UPDATED'
        assert d.ip_address == '10.0.0.2'


def test_delete_device(http, app, sample_client):
    http.post(f'/engineer/clients/{sample_client}/devices/new', data={
        'hostname': 'OLD-PC', 'device_type': 'workstation',
    })
    with app.app_context():
        d = Device.query.filter_by(hostname='OLD-PC').first()
        device_id = d.id

    http.post(f'/engineer/clients/{sample_client}/devices/{device_id}/delete')
    with app.app_context():
        d = Device.query.get(device_id)
        assert not d.is_active


def test_add_credential(http, app, sample_client):
    res = http.post(f'/engineer/clients/{sample_client}/vault/new', data={
        'label': 'Domain Admin',
        'username': 'administrator',
        'password': 'S3cur3P@ss!',
        'service_url': 'https://dc.corp.local',
        'notes': 'Primary domain controller',
    }, follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        cred = Credential.query.filter_by(label='Domain Admin').first()
        assert cred is not None
        assert cred.username == 'administrator'
        assert cred.password_enc != b'S3cur3P@ss!'  # stored encrypted


def test_credential_encrypt_decrypt(app, sample_client):
    with app.app_context():
        cred = Credential(
            client_id=sample_client,
            label='Test',
            username='user',
            password_enc=b'',
        )
        cred.set_password('MySecret123', TEST_VAULT_KEY)
        db.session.add(cred)
        db.session.commit()

        fetched = Credential.query.get(cred.id)
        assert fetched.get_password(TEST_VAULT_KEY) == 'MySecret123'
        assert fetched.password_enc != b'MySecret123'


def test_reveal_credential_endpoint(http, app, sample_client):
    http.post(f'/engineer/clients/{sample_client}/vault/new', data={
        'label': 'Reveal Test',
        'username': 'admin',
        'password': 'RevealMe99',
    })
    with app.app_context():
        cred = Credential.query.filter_by(label='Reveal Test').first()
        cred_id = cred.id

    res = http.post(f'/engineer/clients/{sample_client}/vault/{cred_id}/reveal')
    assert res.status_code == 200
    data = res.get_json()
    assert data['password'] == 'RevealMe99'


def test_delete_credential(http, app, sample_client):
    http.post(f'/engineer/clients/{sample_client}/vault/new', data={
        'label': 'To Delete', 'username': 'u', 'password': 'p',
    })
    with app.app_context():
        cred = Credential.query.filter_by(label='To Delete').first()
        cred_id = cred.id

    http.post(f'/engineer/clients/{sample_client}/vault/{cred_id}/delete')
    with app.app_context():
        assert Credential.query.get(cred_id) is None


def test_device_wrong_client_forbidden(http, app, sample_client):
    # Add a device to sample_client, try editing it via a different client_id
    http.post(f'/engineer/clients/{sample_client}/devices/new', data={
        'hostname': 'TARGET', 'device_type': 'server',
    })
    with app.app_context():
        d = Device.query.filter_by(hostname='TARGET').first()
        device_id = d.id

    wrong_client = sample_client + 999
    res = http.post(f'/engineer/clients/{wrong_client}/devices/{device_id}/edit', data={
        'hostname': 'HACKED', 'device_type': 'server',
    })
    assert res.status_code in (403, 404)
