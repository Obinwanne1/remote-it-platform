# Remote IT Support Platform

A self-hosted IT support platform for managed service providers (MSPs). One engineer supporting multiple client companies — tickets, remote sessions, knowledge base, network inventory, credentials vault, and PDF reporting.

## Features

### Ticket System
- Full lifecycle: New → Assigned → In Progress → Pending Client → Resolved → Closed
- SLA timers per priority (P1=1h, P2=4h, P3=24h, P4=72h) with breach alerts
- Categories, internal engineer notes, client reply thread
- Email notifications on ticket creation, status change, and replies

### Remote Sessions
- Start/end remote sessions per ticket with live timer
- Time logged per ticket, session notes
- AnyDesk one-click connect via `anydesk:<id>` URL scheme

### Knowledge Base
- Markdown articles with live preview editor
- Global articles (all clients) or per-client private articles
- Categories: General, Network, Windows Admin, Security, Training, Hardware, How-To
- Shareable article links for pasting into ticket threads

### Network Inventory (per client)
- Track devices: hostname, IP, type, OS, MAC address, notes
- Device types: router, switch, server, workstation, laptop, printer, firewall

### Credentials Vault (per client)
- Fernet-encrypted passwords at rest
- Reveal on click (never in page source), copy-to-clipboard
- Engineer-only access

### PDF Reports
- Per-client monthly reports: ticket summary, SLA compliance %, remote sessions log, total time
- Download as branded PDF

### Client Health Dashboard
- Per-client stats: open tickets, SLA compliance %, time logged this month

## Roles

| Role | Access |
|------|--------|
| `engineer` | Full platform access |
| `client_admin` | Client portal, submit/view tickets, KB, manage own users |
| `client_staff` | Client portal, submit/view tickets, KB |

## Setup

### Requirements
- Python 3.10+
- pip

### Install

```bash
git clone https://github.com/Obinwanne1/remote-it-platform.git
cd remote-it-platform
pip install -r requirements.txt
```

### Configure

Create a `.env` file:

```env
SECRET_KEY=your-secret-key-here
VAULT_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Optional: email notifications
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=you@gmail.com
```

> **Warning:** Set `VAULT_KEY` before adding any credentials to the vault. Losing this key means losing access to all stored passwords.

### Run

```bash
python app.py
```

App runs at `http://127.0.0.1:5000`

Default engineer login:
- Email: `admin@remoteitsupport.com`
- Password: `changeme123`

**Change the password immediately after first login.**

### Tests

```bash
python -m pytest tests/ -v
```

32 tests covering auth, tickets, sessions, knowledge base, inventory, and reports.

## Stack

- **Backend:** Flask 3, SQLAlchemy, SQLite (dev) / PostgreSQL (prod)
- **Auth:** Session-based (Flask sessions)
- **Email:** Flask-Mail
- **Encryption:** cryptography (Fernet)
- **PDF:** ReportLab
- **Frontend:** Vanilla HTML/CSS/JS, Jinja2 templates
- **Brand:** #407E3C green

## Production Notes

- Switch `SQLALCHEMY_DATABASE_URI` to PostgreSQL
- Set `SECRET_KEY` to a strong random value
- Set `VAULT_KEY` and back it up securely
- Run behind a reverse proxy (nginx) with HTTPS
- Set `FLASK_ENV=production`
