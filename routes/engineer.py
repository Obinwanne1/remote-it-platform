from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, current_app, jsonify, make_response
from models import db, User, Client, Ticket, Comment, RemoteSession, Device, Credential, TICKET_STATUSES, TICKET_CATEGORIES, TICKET_PRIORITIES, DEVICE_TYPES
from datetime import datetime, date
import calendar
from services.email import send_ticket_notification

engineer_bp = Blueprint('engineer', __name__, url_prefix='/engineer')


def engineer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'engineer':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@engineer_bp.route('/dashboard')
@engineer_required
def dashboard():
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    client_filter = request.args.get('client_id', '')

    query = Ticket.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if client_filter:
        query = query.filter_by(client_id=int(client_filter))

    tickets = query.order_by(Ticket.created_at.desc()).all()
    clients = Client.query.filter_by(is_active=True).all()

    open_count = Ticket.query.filter(Ticket.status.notin_(['resolved', 'closed'])).count()
    p1_count = Ticket.query.filter_by(priority='P1').filter(Ticket.status.notin_(['resolved', 'closed'])).count()
    breach_count = sum(1 for t in Ticket.query.filter(Ticket.status.notin_(['resolved', 'closed'])).all()
                       if t.sla_status == 'breached')

    return render_template('engineer/dashboard.html',
                           tickets=tickets,
                           clients=clients,
                           statuses=TICKET_STATUSES,
                           priorities=TICKET_PRIORITIES,
                           open_count=open_count,
                           p1_count=p1_count,
                           breach_count=breach_count,
                           status_filter=status_filter,
                           priority_filter=priority_filter,
                           client_filter=client_filter)


@engineer_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
@engineer_required
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('engineer/ticket_detail.html',
                           ticket=ticket,
                           statuses=TICKET_STATUSES,
                           priorities=TICKET_PRIORITIES,
                           categories=TICKET_CATEGORIES)


@engineer_bp.route('/tickets/<int:ticket_id>/update', methods=['POST'])
@engineer_required
def update_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    old_status = ticket.status

    new_status = request.form.get('status')
    new_priority = request.form.get('priority')
    new_category = request.form.get('category')

    if new_status and new_status != ticket.status:
        ticket.status = new_status
        if new_status == 'resolved':
            ticket.resolved_at = datetime.utcnow()
        elif new_status in ('new', 'assigned', 'in_progress'):
            ticket.resolved_at = None

    if new_priority and new_priority != ticket.priority:
        ticket.priority = new_priority
        ticket.set_sla()

    if new_category:
        ticket.category = new_category

    ticket.updated_at = datetime.utcnow()
    db.session.commit()

    if old_status != ticket.status:
        try:
            send_ticket_notification(ticket, event='status_changed', old_status=old_status)
        except Exception:
            pass

    flash('Ticket updated.', 'success')
    return redirect(url_for('engineer.ticket_detail', ticket_id=ticket_id))


@engineer_bp.route('/tickets/<int:ticket_id>/comment', methods=['POST'])
@engineer_required
def add_comment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    body = request.form.get('body', '').strip()
    is_internal = request.form.get('is_internal') == 'on'

    if not body:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('engineer.ticket_detail', ticket_id=ticket_id))

    comment = Comment(
        ticket_id=ticket_id,
        author_id=session['user_id'],
        body=body,
        is_internal=is_internal
    )
    ticket.updated_at = datetime.utcnow()
    db.session.add(comment)
    db.session.commit()

    if not is_internal:
        try:
            send_ticket_notification(ticket, event='comment_added')
        except Exception:
            pass

    return redirect(url_for('engineer.ticket_detail', ticket_id=ticket_id) + '#comments')


@engineer_bp.route('/clients')
@engineer_required
def clients():
    all_clients = Client.query.order_by(Client.name).all()
    return render_template('engineer/clients.html', clients=all_clients)


@engineer_bp.route('/clients/new', methods=['GET', 'POST'])
@engineer_required
def new_client():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        anydesk_id = request.form.get('anydesk_id', '').strip()
        notes = request.form.get('notes', '').strip()

        if not name or not email:
            flash('Name and email are required.', 'error')
            return render_template('engineer/new_client.html')

        if Client.query.filter_by(email=email).first():
            flash('Client with that email already exists.', 'error')
            return render_template('engineer/new_client.html')

        client = Client(name=name, email=email, phone=phone, anydesk_id=anydesk_id, notes=notes)
        db.session.add(client)
        db.session.commit()
        flash(f'Client "{name}" created.', 'success')
        return redirect(url_for('engineer.client_detail', client_id=client.id))

    return render_template('engineer/new_client.html')


@engineer_bp.route('/clients/<int:client_id>')
@engineer_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    tickets = Ticket.query.filter_by(client_id=client_id).order_by(Ticket.created_at.desc()).all()
    devices = Device.query.filter_by(client_id=client_id, is_active=True).order_by(Device.hostname).all()
    credentials = Credential.query.filter_by(client_id=client_id).order_by(Credential.label).all()
    active_tab = request.args.get('tab', 'overview')

    # Health stats
    open_tickets = [t for t in tickets if t.status not in ('resolved', 'closed')]
    closed_tickets = [t for t in tickets if t.status in ('resolved', 'closed')]
    sla_met = sum(1 for t in closed_tickets if t.resolved_at and t.sla_deadline and t.resolved_at <= t.sla_deadline)
    sla_pct = round(sla_met / len(closed_tickets) * 100) if closed_tickets else 100

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sessions = RemoteSession.query.filter(
        RemoteSession.client_id == client_id,
        RemoteSession.started_at >= month_start,
        RemoteSession.ended_at.isnot(None)
    ).all()
    month_minutes = sum(s.duration_minutes or 0 for s in month_sessions)
    month_h, month_m = divmod(month_minutes, 60)
    month_time_label = f'{month_h}h {month_m}m' if month_h else f'{month_m}m'

    return render_template('engineer/client_detail.html',
                           client=client,
                           tickets=tickets,
                           devices=devices,
                           credentials=credentials,
                           device_types=DEVICE_TYPES,
                           statuses=TICKET_STATUSES,
                           active_tab=active_tab,
                           open_count=len(open_tickets),
                           sla_pct=sla_pct,
                           month_time_label=month_time_label)


@engineer_bp.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@engineer_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        client.name = request.form.get('name', client.name).strip()
        client.email = request.form.get('email', client.email).strip().lower()
        client.phone = request.form.get('phone', '').strip()
        client.anydesk_id = request.form.get('anydesk_id', '').strip()
        client.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Client updated.', 'success')
        return redirect(url_for('engineer.client_detail', client_id=client_id))

    return render_template('engineer/edit_client.html', client=client)


@engineer_bp.route('/tickets/<int:ticket_id>/session/start', methods=['POST'])
@engineer_required
def start_session(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)

    # End any existing active session on this ticket first
    for s in ticket.sessions:
        if s.is_active:
            s.end_session()
            db.session.commit()

    remote_session = RemoteSession(
        ticket_id=ticket_id,
        client_id=ticket.client_id,
        engineer_id=session['user_id'],
        anydesk_id_used=ticket.client.anydesk_id or ''
    )
    db.session.add(remote_session)
    ticket.updated_at = datetime.utcnow()
    if ticket.status == 'assigned':
        ticket.status = 'in_progress'
    db.session.commit()
    flash('Remote session started.', 'success')
    return redirect(url_for('engineer.ticket_detail', ticket_id=ticket_id) + '#sessions')


@engineer_bp.route('/sessions/<int:session_id>/end', methods=['POST'])
@engineer_required
def end_session(session_id):
    remote_session = RemoteSession.query.get_or_404(session_id)
    notes = request.form.get('notes', '').strip()
    remote_session.end_session(notes=notes or None)
    db.session.commit()
    flash(f'Session ended — {remote_session.duration_label} logged.', 'success')
    return redirect(url_for('engineer.ticket_detail', ticket_id=remote_session.ticket_id) + '#sessions')


@engineer_bp.route('/clients/<int:client_id>/users/new', methods=['GET', 'POST'])
@engineer_required
def new_client_user(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'client_staff')

        if role not in ('client_admin', 'client_staff'):
            role = 'client_staff'

        if not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('engineer/new_client_user.html', client=client)

        if User.query.filter_by(email=email).first():
            flash('User with that email already exists.', 'error')
            return render_template('engineer/new_client_user.html', client=client)

        user = User(name=name, email=email, role=role, client_id=client_id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{name}" added to {client.name}.', 'success')
        return redirect(url_for('engineer.client_detail', client_id=client_id))

    return render_template('engineer/new_client_user.html', client=client)


# ── Devices ──────────────────────────────────────────────────────────────────

@engineer_bp.route('/clients/<int:client_id>/devices/new', methods=['POST'])
@engineer_required
def new_device(client_id):
    Client.query.get_or_404(client_id)
    hostname = request.form.get('hostname', '').strip()
    if not hostname:
        flash('Hostname is required.', 'error')
        return redirect(url_for('engineer.client_detail', client_id=client_id, tab='inventory'))

    device = Device(
        client_id=client_id,
        hostname=hostname,
        ip_address=request.form.get('ip_address', '').strip() or None,
        device_type=request.form.get('device_type', 'other'),
        os=request.form.get('os', '').strip() or None,
        mac_address=request.form.get('mac_address', '').strip() or None,
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(device)
    db.session.commit()
    flash(f'Device "{hostname}" added.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='inventory'))


@engineer_bp.route('/clients/<int:client_id>/devices/<int:device_id>/edit', methods=['POST'])
@engineer_required
def edit_device(client_id, device_id):
    device = Device.query.get_or_404(device_id)
    if device.client_id != client_id:
        abort(403)
    device.hostname = request.form.get('hostname', device.hostname).strip()
    device.ip_address = request.form.get('ip_address', '').strip() or None
    device.device_type = request.form.get('device_type', device.device_type)
    device.os = request.form.get('os', '').strip() or None
    device.mac_address = request.form.get('mac_address', '').strip() or None
    device.notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    flash('Device updated.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='inventory'))


@engineer_bp.route('/clients/<int:client_id>/devices/<int:device_id>/delete', methods=['POST'])
@engineer_required
def delete_device(client_id, device_id):
    device = Device.query.get_or_404(device_id)
    if device.client_id != client_id:
        abort(403)
    device.is_active = False
    db.session.commit()
    flash('Device removed.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='inventory'))


# ── Credentials Vault ─────────────────────────────────────────────────────────

@engineer_bp.route('/clients/<int:client_id>/vault/new', methods=['POST'])
@engineer_required
def new_credential(client_id):
    Client.query.get_or_404(client_id)
    label = request.form.get('label', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not label or not username or not password:
        flash('Label, username, and password are required.', 'error')
        return redirect(url_for('engineer.client_detail', client_id=client_id, tab='vault'))

    from flask import current_app
    cred = Credential(
        client_id=client_id,
        label=label,
        username=username,
        service_url=request.form.get('service_url', '').strip() or None,
        notes=request.form.get('notes', '').strip() or None,
        password_enc=b'',
    )
    cred.set_password(password, current_app.config['VAULT_KEY'])
    db.session.add(cred)
    db.session.commit()
    flash(f'Credential "{label}" saved.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='vault'))


@engineer_bp.route('/clients/<int:client_id>/vault/<int:cred_id>/edit', methods=['POST'])
@engineer_required
def edit_credential(client_id, cred_id):
    from flask import current_app
    cred = Credential.query.get_or_404(cred_id)
    if cred.client_id != client_id:
        abort(403)
    cred.label = request.form.get('label', cred.label).strip()
    cred.username = request.form.get('username', cred.username).strip()
    cred.service_url = request.form.get('service_url', '').strip() or None
    cred.notes = request.form.get('notes', '').strip() or None
    new_pw = request.form.get('password', '').strip()
    if new_pw:
        cred.set_password(new_pw, current_app.config['VAULT_KEY'])
    cred.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Credential updated.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='vault'))


@engineer_bp.route('/clients/<int:client_id>/vault/<int:cred_id>/delete', methods=['POST'])
@engineer_required
def delete_credential(client_id, cred_id):
    cred = Credential.query.get_or_404(cred_id)
    if cred.client_id != client_id:
        abort(403)
    db.session.delete(cred)
    db.session.commit()
    flash('Credential deleted.', 'success')
    return redirect(url_for('engineer.client_detail', client_id=client_id, tab='vault'))


@engineer_bp.route('/clients/<int:client_id>/vault/<int:cred_id>/reveal', methods=['POST'])
@engineer_required
def reveal_credential(client_id, cred_id):
    cred = Credential.query.get_or_404(cred_id)
    if cred.client_id != client_id:
        abort(403)
    try:
        plaintext = cred.get_password(current_app.config['VAULT_KEY'])
        return jsonify({'password': plaintext})
    except Exception:
        return jsonify({'error': 'Decryption failed'}), 500


# ── Reports ───────────────────────────────────────────────────────────────────

@engineer_bp.route('/clients/<int:client_id>/report')
@engineer_required
def report_form(client_id):
    client = Client.query.get_or_404(client_id)
    now = datetime.utcnow()
    return render_template('engineer/report_form.html', client=client,
                           current_month=now.month, current_year=now.year)


@engineer_bp.route('/clients/<int:client_id>/report/pdf')
@engineer_required
def report_pdf(client_id):
    client = Client.query.get_or_404(client_id)
    try:
        month = int(request.args.get('month', datetime.utcnow().month))
        year = int(request.args.get('year', datetime.utcnow().year))
    except ValueError:
        abort(400)

    _, last_day = calendar.monthrange(year, month)
    period_start = datetime(year, month, 1)
    period_end = datetime(year, month, last_day, 23, 59, 59)

    tickets = Ticket.query.filter(
        Ticket.client_id == client_id,
        Ticket.created_at >= period_start,
        Ticket.created_at <= period_end
    ).order_by(Ticket.created_at).all()

    sessions = RemoteSession.query.filter(
        RemoteSession.client_id == client_id,
        RemoteSession.started_at >= period_start,
        RemoteSession.started_at <= period_end,
        RemoteSession.ended_at.isnot(None)
    ).order_by(RemoteSession.started_at).all()

    # SLA compliance
    closed = [t for t in tickets if t.status in ('resolved', 'closed')]
    sla_met = sum(1 for t in closed if t.resolved_at and t.sla_deadline and t.resolved_at <= t.sla_deadline)
    sla_pct = round(sla_met / len(closed) * 100) if closed else 100

    total_minutes = sum(s.duration_minutes or 0 for s in sessions)
    th, tm = divmod(total_minutes, 60)
    total_time = f'{th}h {tm}m' if th else f'{tm}m'

    month_name = calendar.month_name[month]

    pdf_bytes = _generate_pdf(client, month_name, year, tickets, sessions,
                              sla_pct, total_time, len(closed))

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'attachment; filename="{client.name.replace(" ", "_")}_{month_name}_{year}.pdf"'
    )
    return response


def _generate_pdf(client, month_name, year, tickets, sessions, sla_pct, total_time, resolved_count):
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)

    GREEN = colors.HexColor('#407E3C')
    LIGHT_GREEN = colors.HexColor('#e8f5e9')
    GREY = colors.HexColor('#6c757d')
    styles = getSampleStyleSheet()

    h1 = ParagraphStyle('h1', parent=styles['Heading1'], textColor=GREEN, fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], textColor=GREEN, fontSize=13, spaceBefore=12, spaceAfter=4)
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, textColor=GREY)

    story = []

    # Header
    story.append(Paragraph(f'IT Support Report', h1))
    story.append(Paragraph(f'{client.name} — {month_name} {year}', styles['Heading2']))
    story.append(Paragraph(f'Generated: {datetime.utcnow().strftime("%d %b %Y %H:%M")} UTC', small))
    story.append(HRFlowable(width='100%', thickness=1, color=GREEN, spaceAfter=8))

    # Summary stats
    story.append(Paragraph('Summary', h2))
    summary_data = [
        ['Tickets Opened', 'Tickets Resolved', 'SLA Compliance', 'Total Remote Time'],
        [str(len(tickets)), str(resolved_count), f'{sla_pct}%', total_time],
    ]
    summary_table = Table(summary_data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GREEN),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREEN]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)

    # Tickets table
    story.append(Paragraph('Tickets', h2))
    if tickets:
        t_data = [['#', 'Title', 'Priority', 'Status', 'Time Logged']]
        for t in tickets:
            t_data.append([
                t.ticket_number,
                Paragraph(t.title[:60], ParagraphStyle('cell', fontSize=8)),
                t.priority,
                t.status_label,
                t.total_time_label,
            ])
        t_table = Table(t_data, colWidths=[22*mm, 70*mm, 18*mm, 28*mm, 22*mm])
        t_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), GREEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GREEN]),
            ('GRID', (0, 0), (-1, -1), 0.3, GREY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t_table)
    else:
        story.append(Paragraph('No tickets in this period.', normal))

    # Sessions table
    story.append(Paragraph('Remote Sessions', h2))
    if sessions:
        s_data = [['Date', 'Duration', 'Ticket', 'Notes']]
        for s in sessions:
            s_data.append([
                s.started_at.strftime('%d %b'),
                s.duration_label,
                f'TKT-{s.ticket_id:04d}',
                Paragraph((s.notes or '—')[:80], ParagraphStyle('snotes', fontSize=7)),
            ])
        s_table = Table(s_data, colWidths=[20*mm, 20*mm, 22*mm, 98*mm])
        s_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), GREEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GREEN]),
            ('GRID', (0, 0), (-1, -1), 0.3, GREY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(s_table)
    else:
        story.append(Paragraph('No remote sessions in this period.', normal))

    # Footer note
    story.append(Spacer(1, 12*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GREY))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph('Remote IT Support — Confidential', small))

    doc.build(story)
    return buf.getvalue()
