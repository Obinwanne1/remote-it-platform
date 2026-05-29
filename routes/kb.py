from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Article, Client, KB_CATEGORIES
from datetime import datetime

kb_bp = Blueprint('kb', __name__)


def engineer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'engineer':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ---- Engineer KB routes ----

@kb_bp.route('/engineer/kb')
@engineer_required
def kb_list():
    category_filter = request.args.get('category', '')
    client_filter = request.args.get('client_id', '')

    query = Article.query.filter_by(is_published=True)
    if category_filter:
        query = query.filter_by(category=category_filter)
    if client_filter:
        query = query.filter_by(client_id=int(client_filter))

    articles = query.order_by(Article.updated_at.desc()).all()
    clients = Client.query.filter_by(is_active=True).all()

    return render_template('engineer/kb_list.html',
                           articles=articles,
                           clients=clients,
                           categories=KB_CATEGORIES,
                           category_filter=category_filter,
                           client_filter=client_filter)


@kb_bp.route('/engineer/kb/new', methods=['GET', 'POST'])
@engineer_required
def kb_new():
    clients = Client.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        category = request.form.get('category', 'General')
        client_id = request.form.get('client_id') or None
        is_published = request.form.get('is_published') == 'on'

        if not title or not body:
            flash('Title and body are required.', 'error')
            return render_template('engineer/kb_form.html',
                                   clients=clients, categories=KB_CATEGORIES, article=None)

        article = Article(
            title=title,
            body=body,
            category=category,
            client_id=int(client_id) if client_id else None,
            is_published=is_published,
            author_id=session['user_id']
        )
        db.session.add(article)
        db.session.commit()
        flash(f'Article "{title}" created.', 'success')
        return redirect(url_for('kb.kb_article', article_id=article.id))

    return render_template('engineer/kb_form.html',
                           clients=clients, categories=KB_CATEGORIES, article=None)


@kb_bp.route('/engineer/kb/<int:article_id>')
@engineer_required
def kb_article(article_id):
    article = Article.query.get_or_404(article_id)
    return render_template('engineer/kb_article.html', article=article)


@kb_bp.route('/engineer/kb/<int:article_id>/edit', methods=['GET', 'POST'])
@engineer_required
def kb_edit(article_id):
    article = Article.query.get_or_404(article_id)
    clients = Client.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        article.title = request.form.get('title', '').strip()
        article.body = request.form.get('body', '').strip()
        article.category = request.form.get('category', 'General')
        client_id = request.form.get('client_id') or None
        article.client_id = int(client_id) if client_id else None
        article.is_published = request.form.get('is_published') == 'on'
        article.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Article updated.', 'success')
        return redirect(url_for('kb.kb_article', article_id=article_id))

    return render_template('engineer/kb_form.html',
                           clients=clients, categories=KB_CATEGORIES, article=article)


@kb_bp.route('/engineer/kb/<int:article_id>/delete', methods=['POST'])
@engineer_required
def kb_delete(article_id):
    article = Article.query.get_or_404(article_id)
    article.is_published = False
    db.session.commit()
    flash('Article unpublished.', 'success')
    return redirect(url_for('kb.kb_list'))


# ---- Client KB routes ----

@kb_bp.route('/portal/kb')
def client_kb():
    if session.get('role') not in ('client_admin', 'client_staff'):
        return redirect(url_for('auth.login'))

    client_id = session['client_id']
    category_filter = request.args.get('category', '')

    # Global public articles + this client's private articles
    from sqlalchemy import or_
    query = Article.query.filter_by(is_published=True).filter(
        or_(Article.client_id == None, Article.client_id == client_id)
    )
    if category_filter:
        query = query.filter_by(category=category_filter)

    articles = query.order_by(Article.updated_at.desc()).all()

    return render_template('client/kb.html',
                           articles=articles,
                           categories=KB_CATEGORIES,
                           category_filter=category_filter)


@kb_bp.route('/portal/kb/<int:article_id>')
def client_kb_article(article_id):
    if session.get('role') not in ('client_admin', 'client_staff'):
        return redirect(url_for('auth.login'))

    client_id = session['client_id']
    article = Article.query.get_or_404(article_id)

    # Only show if global or belongs to this client
    if article.client_id is not None and article.client_id != client_id:
        flash('Access denied.', 'error')
        return redirect(url_for('kb.client_kb'))

    return render_template('client/kb_article.html', article=article)
