from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

db = SQLAlchemy()

SLA_HOURS = {'P1': 1, 'P2': 4, 'P3': 24, 'P4': 72}

TICKET_STATUSES = [
    ('new', 'New'),
    ('assigned', 'Assigned'),
    ('in_progress', 'In Progress'),
    ('pending_client', 'Pending Client'),
    ('resolved', 'Resolved'),
    ('closed', 'Closed'),
]

TICKET_CATEGORIES = [
    'Network', 'Hardware', 'Software', 'Security', 'Training', 'Other'
]

TICKET_PRIORITIES = ['P1', 'P2', 'P3', 'P4']


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    anydesk_id = db.Column(db.String(50))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', backref='client', lazy=True, foreign_keys='User.client_id')
    tickets = db.relationship('Ticket', backref='client', lazy=True)

    @property
    def open_ticket_count(self):
        return sum(1 for t in self.tickets if t.status not in ('resolved', 'closed'))

    @property
    def sla_breach_count(self):
        return sum(1 for t in self.tickets if t.sla_status == 'breached')


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # engineer | client_admin | client_staff
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_engineer(self):
        return self.role == 'engineer'

    @property
    def is_client_admin(self):
        return self.role == 'client_admin'


class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(5), nullable=False, default='P3')
    category = db.Column(db.String(50), default='Other')
    status = db.Column(db.String(30), default='new')
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sla_deadline = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    comments = db.relationship('Comment', backref='ticket', lazy=True, order_by='Comment.created_at')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def set_sla(self):
        hours = SLA_HOURS.get(self.priority, 72)
        self.sla_deadline = datetime.utcnow() + timedelta(hours=hours)

    @property
    def sla_status(self):
        if self.status in ('resolved', 'closed'):
            return 'met'
        if not self.sla_deadline:
            return 'unknown'
        now = datetime.utcnow()
        if now > self.sla_deadline:
            return 'breached'
        remaining_hours = (self.sla_deadline - now).total_seconds() / 3600
        if remaining_hours < 1:
            return 'critical'
        return 'ok'

    @property
    def sla_remaining_label(self):
        if not self.sla_deadline or self.status in ('resolved', 'closed'):
            return ''
        delta = self.sla_deadline - datetime.utcnow()
        total_secs = int(delta.total_seconds())
        if total_secs < 0:
            secs = abs(total_secs)
            h, m = divmod(secs // 60, 60)
            return f'-{h}h {m}m overdue'
        h, m = divmod(total_secs // 60, 60)
        return f'{h}h {m}m remaining'

    @property
    def ticket_number(self):
        return f'TKT-{self.id:04d}'

    @property
    def status_label(self):
        return dict(TICKET_STATUSES).get(self.status, self.status)

    @property
    def priority_color(self):
        return {'P1': '#dc3545', 'P2': '#fd7e14', 'P3': '#407E3C', 'P4': '#6c757d'}.get(self.priority, '#6c757d')

    @property
    def total_session_minutes(self):
        return sum(s.duration_minutes or 0 for s in self.sessions)

    @property
    def total_time_label(self):
        mins = self.total_session_minutes
        if not mins:
            return '0m'
        h, m = divmod(mins, 60)
        return f'{h}h {m}m' if h else f'{m}m'

    @property
    def active_session(self):
        for s in self.sessions:
            if s.is_active:
                return s
        return None


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])


KB_CATEGORIES = ['General', 'Network', 'Windows Admin', 'Security', 'Training', 'Hardware', 'How-To']


class RemoteSession(db.Model):
    __tablename__ = 'remote_sessions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    engineer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)
    notes = db.Column(db.Text)
    anydesk_id_used = db.Column(db.String(50))

    ticket = db.relationship('Ticket', backref='sessions')
    engineer = db.relationship('User', foreign_keys=[engineer_id])

    @property
    def is_active(self):
        return self.ended_at is None

    @property
    def duration_label(self):
        if self.duration_minutes is None:
            return 'Active'
        h, m = divmod(self.duration_minutes, 60)
        return f'{h}h {m}m' if h else f'{m}m'

    def end_session(self, notes=None):
        self.ended_at = datetime.utcnow()
        delta = self.ended_at - self.started_at
        self.duration_minutes = max(1, int(delta.total_seconds() / 60))
        if notes:
            self.notes = notes


class Article(db.Model):
    __tablename__ = 'articles'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='General')
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    is_published = db.Column(db.Boolean, default=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('Client', backref='articles')
    author = db.relationship('User', foreign_keys=[author_id])

    @property
    def is_global(self):
        return self.client_id is None

    @property
    def visibility_label(self):
        if self.client_id is None:
            return 'Global (all clients)'
        return f'Private: {self.client.name}'


DEVICE_TYPES = ['router', 'switch', 'server', 'workstation', 'laptop', 'printer', 'firewall', 'other']


class Device(db.Model):
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    hostname = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(45))
    device_type = db.Column(db.String(30), default='other')
    os = db.Column(db.String(100))
    mac_address = db.Column(db.String(20))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('Client', backref='devices')

    @property
    def type_icon(self):
        icons = {
            'router': '&#128279;',
            'switch': '&#128260;',
            'server': '&#128190;',
            'workstation': '&#128187;',
            'laptop': '&#128187;',
            'printer': '&#128438;',
            'firewall': '&#128737;',
            'other': '&#9000;',
        }
        return icons.get(self.device_type, '&#9000;')


class Credential(db.Model):
    __tablename__ = 'credentials'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    password_enc = db.Column(db.LargeBinary, nullable=False)
    service_url = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('Client', backref='credentials')

    def set_password(self, plaintext, vault_key):
        f = Fernet(vault_key)
        self.password_enc = f.encrypt(plaintext.encode('utf-8'))

    def get_password(self, vault_key):
        f = Fernet(vault_key)
        return f.decrypt(self.password_enc).decode('utf-8')
