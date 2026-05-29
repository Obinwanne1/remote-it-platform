from flask import current_app
from flask_mail import Mail, Message

mail = Mail()


def send_ticket_notification(ticket, event='created', old_status=None):
    """Send email notifications for ticket events."""
    if current_app.config.get('MAIL_SUPPRESS_SEND'):
        return

    client = ticket.client
    engineer_email = current_app.config.get('DEFAULT_ENGINEER_EMAIL')

    subjects = {
        'created': f'[{ticket.ticket_number}] New Ticket: {ticket.title}',
        'status_changed': f'[{ticket.ticket_number}] Status Updated: {ticket.title}',
        'comment_added': f'[{ticket.ticket_number}] New Reply: {ticket.title}',
        'client_replied': f'[{ticket.ticket_number}] Client Replied: {ticket.title}',
    }

    subject = subjects.get(event, f'[{ticket.ticket_number}] Update: {ticket.title}')

    if event == 'created':
        # Notify engineer
        _send(
            to=engineer_email,
            subject=subject,
            body=f"""New ticket submitted by {client.name}.

Ticket: {ticket.ticket_number}
Title: {ticket.title}
Priority: {ticket.priority}
Category: {ticket.category}

Description:
{ticket.description}
"""
        )
    elif event == 'status_changed':
        # Notify client
        _notify_client_users(client, subject,
            f"""Your ticket status has been updated.

Ticket: {ticket.ticket_number}
Title: {ticket.title}
Status: {old_status} → {ticket.status_label}

Log in to your portal to view details.
""")
    elif event == 'comment_added':
        # Notify client of engineer reply
        _notify_client_users(client, subject,
            f"""Your IT engineer has replied to your ticket.

Ticket: {ticket.ticket_number}
Title: {ticket.title}

Log in to your portal to read the reply.
""")
    elif event == 'client_replied':
        # Notify engineer
        _send(
            to=engineer_email,
            subject=subject,
            body=f"""Client {client.name} replied to ticket {ticket.ticket_number}.

Title: {ticket.title}

Log in to your dashboard to view.
"""
        )


def _notify_client_users(client, subject, body):
    from models import User
    recipients = [u.email for u in client.users if u.is_active]
    for email in recipients:
        _send(to=email, subject=subject, body=body)


def _send(to, subject, body):
    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f'Email send failed: {e}')
