from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Ticket, Comment, Client, TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_STATUSES
from datetime import datetime
from services.email import send_ticket_notification

client_bp = Blueprint('client', __name__, url_prefix='/portal')


def client_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('client_admin', 'client_staff'):
            return redirect(url_for('auth.login'))
        if not session.get('client_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@client_bp.route('/')
@client_required
def portal():
    client_id = session['client_id']
    status_filter = request.args.get('status', '')

    query = Ticket.query.filter_by(client_id=client_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    tickets = query.order_by(Ticket.created_at.desc()).all()
    client = Client.query.get(client_id)

    open_count = Ticket.query.filter_by(client_id=client_id).filter(
        Ticket.status.notin_(['resolved', 'closed'])).count()
    resolved_count = Ticket.query.filter_by(client_id=client_id).filter(
        Ticket.status.in_(['resolved', 'closed'])).count()

    return render_template('client/portal.html',
                           tickets=tickets,
                           client=client,
                           statuses=TICKET_STATUSES,
                           open_count=open_count,
                           resolved_count=resolved_count,
                           status_filter=status_filter)


@client_bp.route('/tickets/new', methods=['GET', 'POST'])
@client_required
def new_ticket():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        priority = request.form.get('priority', 'P3')
        category = request.form.get('category', 'Other')

        if not title or not description:
            flash('Title and description are required.', 'error')
            return render_template('client/new_ticket.html',
                                   categories=TICKET_CATEGORIES,
                                   priorities=TICKET_PRIORITIES)

        if priority not in TICKET_PRIORITIES:
            priority = 'P3'

        ticket = Ticket(
            title=title,
            description=description,
            priority=priority,
            category=category,
            status='new',
            client_id=session['client_id'],
            created_by_id=session['user_id']
        )
        ticket.set_sla()
        db.session.add(ticket)
        db.session.commit()

        try:
            send_ticket_notification(ticket, event='created')
        except Exception:
            pass

        flash(f'Ticket {ticket.ticket_number} submitted successfully.', 'success')
        return redirect(url_for('client.ticket_detail', ticket_id=ticket.id))

    return render_template('client/new_ticket.html',
                           categories=TICKET_CATEGORIES,
                           priorities=TICKET_PRIORITIES)


@client_bp.route('/tickets/<int:ticket_id>')
@client_required
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.client_id != session['client_id']:
        flash('Access denied.', 'error')
        return redirect(url_for('client.portal'))

    visible_comments = [c for c in ticket.comments if not c.is_internal]
    return render_template('client/ticket_detail.html',
                           ticket=ticket,
                           comments=visible_comments)


@client_bp.route('/tickets/<int:ticket_id>/comment', methods=['POST'])
@client_required
def add_comment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.client_id != session['client_id']:
        flash('Access denied.', 'error')
        return redirect(url_for('client.portal'))

    body = request.form.get('body', '').strip()
    if not body:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('client.ticket_detail', ticket_id=ticket_id))

    comment = Comment(
        ticket_id=ticket_id,
        author_id=session['user_id'],
        body=body,
        is_internal=False
    )
    ticket.updated_at = datetime.utcnow()

    # If client replies, move back from pending_client
    if ticket.status == 'pending_client':
        ticket.status = 'in_progress'

    db.session.add(comment)
    db.session.commit()

    try:
        send_ticket_notification(ticket, event='client_replied')
    except Exception:
        pass

    return redirect(url_for('client.ticket_detail', ticket_id=ticket_id) + '#comments')
