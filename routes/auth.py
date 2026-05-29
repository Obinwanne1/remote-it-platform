from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return _redirect_by_role(session.get('role'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email, is_active=True).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            session['client_id'] = user.client_id
            return _redirect_by_role(user.role)

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


def _redirect_by_role(role):
    if role == 'engineer':
        return redirect(url_for('engineer.dashboard'))
    return redirect(url_for('client.portal'))
