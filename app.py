import os
import mimetypes
import sqlite3
import zipfile
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(Config.DATABASE_PATH)
UPLOAD_FOLDER = Path(Config.UPLOAD_FOLDER)
INSTANCE_FOLDER = Path(Config.INSTANCE_FOLDER)

CATEGORY_CHOICES = [
    'Staircase Work',
    'Handrail Work',
    'Sitout Work',
    'Glass Work',
    'Gate and Grill Work',
    'Roofing and Shed Work',
    'Door and Window Work',
    'Balcony Work',
    'Stainless Steel Fabrication',
    'Aluminium Fabrication',
    'Other Works',
]

STATUS_CHOICES = ['New', 'Pending', 'In Progress', 'Completed', 'On Hold']
MEDIA_CATEGORIES = ['Before Work', 'Work in Progress', 'Completed Work', 'Reference', 'Video', 'Other']


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        return self.connection.execute(query.replace('?', '%s'), params)

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)

    def __getattr__(self, name):
        return getattr(self.connection, name)


def get_db_connection():
    if Config.DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(Config.DATABASE_URL, row_factory=dict_row)
        return PostgresConnection(connection)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def ensure_directories():
    if not Config.DATABASE_URL:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not Config.BLOB_STORAGE_ENABLED:
        UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        for category in ['images', 'videos']:
            (UPLOAD_FOLDER / category).mkdir(exist_ok=True)
    if not os.environ.get('VERCEL'):
        INSTANCE_FOLDER.mkdir(parents=True, exist_ok=True)


def adapt_schema_for_postgres(schema):
    return (
        schema.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY')
        .replace('INTEGER', 'BIGINT')
        .replace(' REAL', ' DOUBLE PRECISION')
        .replace(
            "TEXT NOT NULL DEFAULT (datetime('now'))",
            'TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP',
        )
    )


def init_db():
    ensure_directories()
    conn = get_db_connection()
    schema = '''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            alt_phone TEXT,
            location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_ref TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            start_date TEXT,
            expected_completion TEXT,
            status TEXT NOT NULL DEFAULT 'New',
            estimated_price REAL,
            advance_amount REAL,
            balance_amount REAL,
            internal_notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            category TEXT NOT NULL,
            file_name TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS showcase_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_category TEXT NOT NULL,
            media_type TEXT NOT NULL,
            category TEXT NOT NULL,
            file_name TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS customer_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        '''
    if Config.DATABASE_URL:
        schema = adapt_schema_for_postgres(schema)
    conn.executescript(schema)
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_db_connection()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    return row['value']


def set_setting(key, value):
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def ensure_admin_account():
    username = os.environ.get('ADMIN_USERNAME') or 'SMARTSTEEL'
    password = os.environ.get('ADMIN_PASSWORD')
    conn = get_db_connection()
    existing = conn.execute('SELECT username FROM admin_users WHERE username = ?', (username,)).fetchone()
    if existing is None:
        if not password:
            if os.environ.get('VERCEL'):
                conn.close()
                raise RuntimeError('Set ADMIN_PASSWORD in the Vercel project environment variables before deploying.')
            password = str(uuid4())[:12]
            setup_path = INSTANCE_FOLDER / 'admin_credentials.txt'
            with open(setup_path, 'w', encoding='utf-8') as fh:
                fh.write(f'Username: {username}\nPassword: {password}\n')
            print(f'Admin credentials created. Username: {username}, Password: {password}')
            print(f'Credentials saved to: {setup_path}')
        conn.execute(
            'INSERT INTO admin_users(username, password_hash) VALUES(?, ?)',
            (username, generate_password_hash(password)),
        )
        conn.commit()
    else:
        if password:
            conn.execute(
                'UPDATE admin_users SET password_hash = ? WHERE username = ?',
                (generate_password_hash(password), username),
            )
            conn.commit()
    conn.close()


def generate_project_reference():
    conn = get_db_connection()
    last_row = conn.execute('SELECT project_ref FROM projects ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    year = datetime.now().strftime('%Y')
    if last_row is None:
        sequence = 1
    else:
        suffix = last_row['project_ref'].split('-')[-1]
        try:
            sequence = int(suffix) + 1
        except (ValueError, IndexError):
            sequence = 1
    return f'PRJ-{year}-{sequence:04d}'


def get_customer_by_name_phone(name, phone):
    conn = get_db_connection()
    row = conn.execute(
        'SELECT * FROM customers WHERE lower(trim(name)) = lower(trim(?)) AND phone = ?',
        (name, phone),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_or_create_customer(name, phone, alt_phone='', location='', notes=''):
    cleaned_name = (name or '').strip()
    cleaned_phone = (phone or '').strip()
    if not cleaned_name or not cleaned_phone:
        raise ValueError('Customer name and phone number are required.')

    existing = get_customer_by_name_phone(cleaned_name, cleaned_phone)
    if existing:
        return existing['id']

    conn = get_db_connection()
    row = conn.execute(
        'INSERT INTO customers(name, phone, alt_phone, location, notes) VALUES(?, ?, ?, ?, ?) RETURNING id',
        (cleaned_name, cleaned_phone, alt_phone, location, notes),
    ).fetchone()
    conn.commit()
    customer_id = row['id']
    conn.close()
    return customer_id


def normalize_media_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in Config.ALLOWED_IMAGE_EXTENSIONS:
        return 'image'
    if ext in Config.ALLOWED_VIDEO_EXTENSIONS:
        return 'video'
    return None


def save_uploaded_media(project_id, files, category='Other'):
    saved = []
    project_dir = UPLOAD_FOLDER / f'project_{project_id}'
    if not Config.BLOB_STORAGE_ENABLED:
        project_dir.mkdir(exist_ok=True)

    for file in files:
        if file is None or file.filename == '':
            continue

        media_type = normalize_media_type(file.filename)
        if media_type is None:
            raise ValueError(f'Unsupported file type: {file.filename}')

        if file.content_length and file.content_length > Config.MAX_CONTENT_LENGTH:
            raise ValueError(f'File exceeds the allowed size limit: {file.filename}')

        safe_name = secure_filename(file.filename)
        if not safe_name:
            safe_name = f'{uuid4().hex}{os.path.splitext(file.filename)[1].lower()}'
        safe_name = safe_name.replace(' ', '_')
        unique_name = f'{uuid4().hex}_{safe_name}'
        if Config.BLOB_STORAGE_ENABLED:
            from vercel.blob import sync as blob

            blob_result = blob.put_blob(
                f'projects/{project_id}/{media_type}/{unique_name}',
                file.read(),
                access='public',
                content_type=mimetypes.guess_type(file.filename)[0] or 'application/octet-stream',
            )
            stored_path = blob_result.url
        else:
            dest_dir = project_dir / media_type
            dest_dir.mkdir(exist_ok=True)
            dest_path = dest_dir / unique_name
            file.save(dest_path)
            stored_path = str(dest_path.relative_to(BASE_DIR)).replace('\\', '/')

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO project_media(project_id, media_type, category, file_name, original_name, file_path) VALUES(?, ?, ?, ?, ?, ?)',
            (
                project_id,
                media_type,
                category,
                unique_name,
                file.filename,
                stored_path,
            ),
        )
        conn.commit()
        conn.close()
        saved.append(stored_path)

    return saved


def save_showcase_photos(files, work_category, category='Reference'):
    showcase_dir = UPLOAD_FOLDER / 'showcase' / 'image'
    if not Config.BLOB_STORAGE_ENABLED:
        showcase_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for file in files:
        if file is None or file.filename == '':
            continue

        if normalize_media_type(file.filename) != 'image':
            raise ValueError(f'Only photo files can be added to the portfolio: {file.filename}')

        safe_name = secure_filename(file.filename)
        if not safe_name:
            safe_name = f'{uuid4().hex}{os.path.splitext(file.filename)[1].lower()}'
        unique_name = f'{uuid4().hex}_{safe_name.replace(" ", "_")}'
        if Config.BLOB_STORAGE_ENABLED:
            from vercel.blob import sync as blob

            blob_result = blob.put_blob(
                f'showcase/image/{unique_name}',
                file.read(),
                access='public',
                content_type=mimetypes.guess_type(file.filename)[0] or 'application/octet-stream',
            )
            stored_path = blob_result.url
        else:
            dest_path = showcase_dir / unique_name
            file.save(dest_path)
            stored_path = str(dest_path.relative_to(BASE_DIR)).replace('\\', '/')

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO showcase_media(work_category, media_type, category, file_name, original_name, file_path) VALUES(?, ?, ?, ?, ?, ?)',
            (
                work_category,
                'image',
                category,
                unique_name,
                file.filename,
                stored_path,
            ),
        )
        conn.commit()
        conn.close()
        saved.append(stored_path)

    return saved


def delete_stored_file(file_path):
    parsed = urlparse(file_path)
    if parsed.scheme:
        if parsed.scheme == 'https' and parsed.hostname and parsed.hostname.endswith('.public.blob.vercel-storage.com'):
            from vercel.blob import sync as blob

            blob.delete_blob(file_path)
            return
        raise ValueError('Cannot delete media from an unrecognized storage URL.')

    local_path = BASE_DIR / file_path
    if local_path.exists():
        local_path.unlink()


def get_project_by_id(project_id):
    conn = get_db_connection()
    project = conn.execute(
        '''
        SELECT p.*, c.name as customer_name, c.phone as customer_phone, c.alt_phone as customer_alt_phone, c.location as customer_location
        FROM projects p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.id = ?
        ''',
        (project_id,),
    ).fetchone()
    conn.close()
    if project is None:
        return None
    return dict(project)


def get_media_for_project(project_id):
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM project_media WHERE project_id = ? ORDER BY created_at DESC',
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def get_csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = uuid4().hex
        session['csrf_token'] = token
    return token


def validate_csrf_form():
    token = request.form.get('csrf_token')
    if token != session.get('csrf_token'):
        abort(400)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    if os.environ.get('VERCEL'):
        required_environment = {
            'DATABASE_URL': Config.DATABASE_URL,
            'Vercel Blob credentials': Config.BLOB_STORAGE_ENABLED,
            'FLASK_SECRET_KEY': os.environ.get('FLASK_SECRET_KEY'),
            'ADMIN_PASSWORD': os.environ.get('ADMIN_PASSWORD'),
        }
        missing = [name for name, value in required_environment.items() if not value]
        if missing:
            raise RuntimeError(
                'Missing required Vercel environment variables: ' + ', '.join(missing)
            )
    init_db()
    ensure_admin_account()
    app.jinja_env.globals['category_choices'] = CATEGORY_CHOICES
    app.jinja_env.globals['status_choices'] = STATUS_CHOICES
    app.jinja_env.globals['media_categories'] = MEDIA_CATEGORIES
    app.jinja_env.globals['project_ref'] = lambda p: p.get('project_ref', 'N/A')
    app.jinja_env.globals['csrf_token'] = get_csrf_token

    @app.before_request
    def ensure_csrf_token():
        if request.method == 'POST' and request.endpoint not in ('login', 'backup_database', 'delete_project', 'delete_customer', 'delete_media'):
            if 'logged_in' not in session:
                return redirect(url_for('login', next=request.path))
            if request.form.get('csrf_token') != session.get('csrf_token'):
                abort(400)

    @app.route('/login')
    def public_login_redirect():
        return redirect(url_for('dashboard'))

    @app.route('/admin/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM admin_users WHERE username = ?', (username,)).fetchone()
            conn.close()

            if user and check_password_hash(user['password_hash'], password):
                session.clear()
                session['logged_in'] = True
                session['username'] = username
                session['csrf_token'] = uuid4().hex
                flash('Login successful.', 'success')
                next_page = request.args.get('next', '')
                if next_page.startswith('/') and not next_page.startswith('//'):
                    return redirect(next_page)
                return redirect(url_for('dashboard'))

            flash('Invalid username or password.', 'danger')

        return render_template('login.html')

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        if filename.startswith('https://'):
            parsed = urlparse(filename)
            if parsed.hostname and parsed.hostname.endswith('.public.blob.vercel-storage.com'):
                return redirect(filename)
            abort(404)
        return send_from_directory(UPLOAD_FOLDER, filename)

    @app.route('/')
    @app.route('/dashboard')
    def dashboard():
        conn = get_db_connection()
        totals = {
            'projects': conn.execute('SELECT COUNT(*) as total FROM projects').fetchone()['total'],
            'ongoing': conn.execute("SELECT COUNT(*) as total FROM projects WHERE status = 'In Progress'").fetchone()['total'],
            'completed': conn.execute("SELECT COUNT(*) as total FROM projects WHERE status = 'Completed'").fetchone()['total'],
            'pending': conn.execute("SELECT COUNT(*) as total FROM projects WHERE status = 'Pending'").fetchone()['total'],
            'media': conn.execute('SELECT COUNT(*) as total FROM project_media').fetchone()['total'],
        }
        recent = conn.execute(
            '''
            SELECT p.id, p.project_ref, p.title, p.category, p.status,
                (SELECT m.file_path FROM project_media m
                 WHERE m.project_id = p.id AND m.media_type = 'image'
                 ORDER BY m.created_at DESC LIMIT 1) AS cover_image
            FROM projects p
            ORDER BY p.created_at DESC
            LIMIT 6
            ''',
        ).fetchall()
        featured_media = conn.execute(
            '''
            SELECT file_path, media_type, category, project_title AS title, project_category
            FROM (
                SELECT m.file_path, m.media_type, m.category, p.title AS project_title,
                    p.category AS project_category, m.created_at
                FROM project_media m
                JOIN projects p ON p.id = m.project_id
                WHERE m.media_type = 'image'
                UNION ALL
                SELECT file_path, media_type, category, 'Portfolio Photo' AS project_title,
                    work_category AS project_category, created_at
                FROM showcase_media
                WHERE media_type = 'image'
            )
            ORDER BY created_at DESC
            LIMIT 1
            '''
        ).fetchone()
        conn.close()
        return render_template(
            'dashboard.html',
            totals=totals,
            recent_projects=recent,
            featured_media=featured_media,
        )

    @app.route('/logout')
    @login_required
    def logout():
        session.clear()
        flash('You have been logged out.', 'info')
        return redirect(url_for('dashboard'))

    @app.route('/customers')
    @login_required
    def customers():
        q = request.args.get('q', '').strip()
        conn = get_db_connection()
        if q:
            sql = '''
                SELECT c.*, COUNT(p.id) as project_count
                FROM customers c
                LEFT JOIN projects p ON p.customer_id = c.id
                WHERE lower(c.name) LIKE lower(?) OR c.phone LIKE ?
                GROUP BY c.id
                ORDER BY c.name ASC
            '''
            rows = conn.execute(sql, (f'%{q}%', f'%{q}%')).fetchall()
        else:
            rows = conn.execute(
                '''
                SELECT c.*, COUNT(p.id) as project_count
                FROM customers c
                LEFT JOIN projects p ON p.customer_id = c.id
                GROUP BY c.id
                ORDER BY c.name ASC
                '''
            ).fetchall()
        conn.close()
        return render_template('customers/customers.html', customers=rows, query=q)

    @app.route('/customers/new', methods=['GET', 'POST'])
    @login_required
    def customer_new():
        if request.method == 'POST':
            validate_csrf_form()
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            alt_phone = request.form.get('alt_phone', '').strip()
            location = request.form.get('location', '').strip()
            notes = request.form.get('notes', '').strip()
            if not name or not phone:
                flash('Customer name and phone number are required.', 'danger')
            else:
                customer_id = get_or_create_customer(name, phone, alt_phone, location, notes)
                flash('Customer saved successfully.', 'success')
                return redirect(url_for('customer_detail', customer_id=customer_id))
        return render_template('customers/customer_form.html', customer=None)

    @app.route('/customers/<int:customer_id>', methods=['GET'])
    @login_required
    def customer_detail(customer_id):
        conn = get_db_connection()
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
        projects = conn.execute(
            '''
            SELECT p.*, COUNT(m.id) as media_count
            FROM projects p
            LEFT JOIN project_media m ON m.project_id = p.id
            WHERE p.customer_id = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
            ''',
            (customer_id,),
        ).fetchall()
        conn.close()
        if customer is None:
            abort(404)
        return render_template('customers/customer_detail.html', customer=dict(customer), projects=projects)

    @app.route('/customers/<int:customer_id>/edit', methods=['GET', 'POST'])
    @login_required
    def customer_edit(customer_id):
        conn = get_db_connection()
        customer = conn.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
        conn.close()
        if customer is None:
            abort(404)

        if request.method == 'POST':
            validate_csrf_form()
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            alt_phone = request.form.get('alt_phone', '').strip()
            location = request.form.get('location', '').strip()
            notes = request.form.get('notes', '').strip()

            conn = get_db_connection()
            conn.execute(
                'UPDATE customers SET name = ?, phone = ?, alt_phone = ?, location = ?, notes = ? WHERE id = ?',
                (name, phone, alt_phone, location, notes, customer_id),
            )
            conn.commit()
            conn.close()
            flash('Customer updated successfully.', 'success')
            return redirect(url_for('customer_detail', customer_id=customer_id))

        return render_template('customers/customer_form.html', customer=dict(customer))

    @app.route('/customers/<int:customer_id>/delete', methods=['POST'])
    @login_required
    def delete_customer(customer_id):
        validate_csrf_form()
        conn = get_db_connection()
        conn.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
        conn.commit()
        conn.close()
        flash('Customer deleted successfully.', 'success')
        return redirect(url_for('customers'))

    @app.route('/projects')
    def projects():
        search = request.args.get('q', '').strip()
        category = request.args.get('category', 'All')
        status = request.args.get('status', 'All')
        from_date = request.args.get('from_date', '').strip()
        to_date = request.args.get('to_date', '').strip()
        sort = request.args.get('sort', 'newest')

        conn = get_db_connection()
        sql = '''
            SELECT p.id, p.project_ref, p.title, p.category, p.status, p.created_at,
                COUNT(m.id) as media_count
            FROM projects p
            LEFT JOIN project_media m ON m.project_id = p.id
            WHERE 1=1
        '''
        params = []
        if search:
            sql += ' AND (lower(p.title) LIKE lower(?) OR p.project_ref LIKE ? ) '
            params.extend([f'%{search}%', f'%{search}%'])
        if category != 'All':
            sql += ' AND p.category = ? '
            params.append(category)
        if status != 'All':
            sql += ' AND p.status = ? '
            params.append(status)
        if from_date:
            sql += ' AND date(p.created_at) >= date(?) '
            params.append(from_date)
        if to_date:
            sql += ' AND date(p.created_at) <= date(?) '
            params.append(to_date)
        sql += ' GROUP BY p.id '
        if sort == 'oldest':
            sql += ' ORDER BY p.created_at ASC'
        elif sort == 'status':
            sql += ' ORDER BY CASE p.status WHEN "New" THEN 1 WHEN "Pending" THEN 2 WHEN "In Progress" THEN 3 WHEN "Completed" THEN 4 WHEN "On Hold" THEN 5 ELSE 6 END ASC'
        else:
            sql += ' ORDER BY p.created_at DESC'
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return render_template('projects/projects.html', projects=rows, search=search, category=category, status=status, from_date=from_date, to_date=to_date, sort=sort)

    @app.route('/projects/new', methods=['GET', 'POST'])
    @login_required
    def project_new():
        if request.method == 'POST':
            validate_csrf_form()
            try:
                customer_name = request.form.get('customer_name', '').strip()
                customer_phone = request.form.get('customer_phone', '').strip()
                alt_phone = request.form.get('alt_phone', '').strip()
                customer_location = request.form.get('customer_location', '').strip()
                customer_notes = request.form.get('customer_notes', '').strip()
                title = request.form.get('title', '').strip()
                category = request.form.get('category')
                media_category = request.form.get('media_category', 'Other')
                location = request.form.get('location', '').strip()
                description = request.form.get('description', '').strip()
                start_date = request.form.get('start_date', '')
                expected_completion = request.form.get('expected_completion', '')
                status = request.form.get('status', 'New')
                estimated_price = request.form.get('estimated_price', '')
                advance_amount = request.form.get('advance_amount', '')
                internal_notes = request.form.get('internal_notes', '').strip()

                if not title or not customer_name or not customer_phone or not category or not location:
                    raise ValueError('Project title, customer name, customer phone, and category are required.')
                if category not in CATEGORY_CHOICES:
                    raise ValueError('Select a valid work category.')
                if status not in STATUS_CHOICES:
                    raise ValueError('Select a valid project status.')
                if media_category not in MEDIA_CATEGORIES:
                    raise ValueError('Select a valid media category.')

                files = request.files.getlist('media_files')
                for file in files:
                    if file.filename and normalize_media_type(file.filename) is None:
                        raise ValueError(f'Unsupported file type: {file.filename}')

                customer_id = get_or_create_customer(customer_name, customer_phone, alt_phone, customer_location, customer_notes)
                project_ref = generate_project_reference()
                estimated = float(estimated_price) if estimated_price else 0.0
                advance = float(advance_amount) if advance_amount else 0.0
                balance = estimated - advance
                conn = get_db_connection()
                project_row = conn.execute(
                    '''
                    INSERT INTO projects(
                        project_ref, title, customer_id, category, location, description, start_date,
                        expected_completion, status, estimated_price, advance_amount, balance_amount, internal_notes
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
                    ''',
                    (project_ref, title, customer_id, category, location, description, start_date, expected_completion, status, estimated, advance, balance, internal_notes),
                ).fetchone()
                project_id = project_row['id']
                conn.commit()
                conn.close()

                if files:
                    save_uploaded_media(project_id, files, category=media_category)
                flash(f'Project {project_ref} created successfully.', 'success')
                return redirect(url_for('project_detail', project_id=project_id))
            except ValueError as exc:
                flash(str(exc), 'danger')
        return render_template('projects/project_form.html', project=None, categories=CATEGORY_CHOICES, status_choices=STATUS_CHOICES)

    @app.route('/admin/upload', methods=['GET', 'POST'])
    @login_required
    def admin_upload():
        selected_project_id = request.values.get('project_id', type=int)
        selected_category = request.values.get('media_category', 'Completed Work')
        selected_work_category = request.values.get('work_category', '')

        if request.method == 'POST':
            validate_csrf_form()
            project_id = request.form.get('project_id', type=int)
            selected_project_id = project_id
            selected_category = request.form.get('media_category', 'Completed Work')
            selected_work_category = request.form.get('work_category', '')
            files = request.files.getlist('media_files')

            if selected_work_category not in CATEGORY_CHOICES:
                flash('Choose a valid work category.', 'danger')
            elif selected_category not in MEDIA_CATEGORIES:
                flash('Choose a valid photo or video stage.', 'danger')
            elif not files or not any(file.filename for file in files):
                flash('Choose at least one photo or video to upload.', 'warning')
            elif any(file.filename and normalize_media_type(file.filename) is None for file in files):
                flash('Unsupported file type. Use JPG, JPEG, PNG, WEBP, MP4, or WEBM files.', 'danger')
            else:
                conn = get_db_connection()
                project = conn.execute(
                    'SELECT id, title, category FROM projects WHERE id = ?',
                    (project_id,),
                ).fetchone()
                conn.close()
                if project is None:
                    flash('Choose an existing project for these photos or videos.', 'danger')
                elif project['category'] != selected_work_category:
                    flash('Choose a project that matches the selected work category.', 'danger')
                else:
                    try:
                        save_uploaded_media(project_id, files, category=selected_category)
                    except ValueError as exc:
                        flash(str(exc), 'danger')
                    else:
                        flash(f'Work photos and videos added to {project["title"]}.', 'success')
                        return redirect(url_for('project_detail', project_id=project_id))

        conn = get_db_connection()
        projects_for_upload = conn.execute(
            'SELECT id, project_ref, title, category FROM projects ORDER BY created_at DESC',
        ).fetchall()
        conn.close()
        return render_template(
            'admin_upload.html',
            projects=projects_for_upload,
            selected_project_id=selected_project_id,
            selected_category=selected_category,
            selected_work_category=selected_work_category,
        )

    @app.route('/admin/upload-showcase', methods=['GET', 'POST'])
    @login_required
    def upload_showcase():
        selected_work_category = request.values.get('work_category', '')
        selected_category = request.values.get('media_category', 'Reference')

        if request.method == 'POST':
            validate_csrf_form()
            selected_work_category = request.form.get('work_category', '')
            selected_category = request.form.get('media_category', 'Reference')
            files = request.files.getlist('media_files')

            if selected_work_category not in CATEGORY_CHOICES:
                flash('Choose a valid work category.', 'danger')
            elif selected_category not in MEDIA_CATEGORIES:
                flash('Choose a valid photo stage.', 'danger')
            elif not files or not any(file.filename for file in files):
                flash('Choose at least one photo to upload.', 'warning')
            elif any(file.filename and normalize_media_type(file.filename) != 'image' for file in files):
                flash('Portfolio uploads accept photo files only: JPG, JPEG, PNG, or WEBP.', 'danger')
            else:
                try:
                    save_showcase_photos(files, selected_work_category, category=selected_category)
                except ValueError as exc:
                    flash(str(exc), 'danger')
                else:
                    flash('Portfolio photos added to the public gallery. No customer details were saved.', 'success')
                    return redirect(url_for('gallery', category=selected_work_category))

        return render_template(
            'admin_showcase_upload.html',
            selected_work_category=selected_work_category,
            selected_category=selected_category,
        )

    @app.route('/projects/<int:project_id>')
    def project_detail(project_id):
        project = get_project_by_id(project_id)
        if project is None:
            abort(404)
        media = get_media_for_project(project_id)
        conn = get_db_connection()
        customer_projects = []
        if 'logged_in' in session:
            customer_projects = conn.execute(
                'SELECT p.id, p.title, p.status FROM projects p WHERE p.customer_id = ? ORDER BY p.created_at DESC LIMIT 5',
                (project['customer_id'],),
            ).fetchall()
        conn.close()
        return render_template(
            'projects/project_detail.html',
            project=project,
            media=media,
            customer_projects=customer_projects,
            is_admin='logged_in' in session,
        )

    @app.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
    @login_required
    def project_edit(project_id):
        existing = get_project_by_id(project_id)
        if existing is None:
            abort(404)

        if request.method == 'POST':
            validate_csrf_form()
            try:
                title = request.form.get('title', '').strip()
                category = request.form.get('category')
                location = request.form.get('location', '').strip()
                description = request.form.get('description', '').strip()
                start_date = request.form.get('start_date', '')
                expected_completion = request.form.get('expected_completion', '')
                status = request.form.get('status', 'New')
                estimated_price = request.form.get('estimated_price', '')
                advance_amount = request.form.get('advance_amount', '')
                internal_notes = request.form.get('internal_notes', '').strip()

                estimated = float(estimated_price) if estimated_price else 0.0
                advance = float(advance_amount) if advance_amount else 0.0
                balance = estimated - advance

                conn = get_db_connection()
                conn.execute(
                    '''
                    UPDATE projects SET title = ?, category = ?, location = ?, description = ?, start_date = ?,
                    expected_completion = ?, status = ?, estimated_price = ?, advance_amount = ?, balance_amount = ?, internal_notes = ?, updated_at = ?
                    WHERE id = ?
                    ''',
                    (title, category, location, description, start_date, expected_completion, status, estimated, advance, balance, internal_notes, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), project_id),
                )
                conn.commit()
                conn.close()
                flash('Project updated successfully.', 'success')
                return redirect(url_for('project_detail', project_id=project_id))
            except ValueError:
                flash('Please enter valid numeric values.', 'danger')

        return render_template('projects/project_form.html', project=existing, categories=CATEGORY_CHOICES, status_choices=STATUS_CHOICES)

    @app.route('/projects/<int:project_id>/delete', methods=['POST'])
    @login_required
    def delete_project(project_id):
        validate_csrf_form()
        conn = get_db_connection()
        project = conn.execute('SELECT project_ref FROM projects WHERE id = ?', (project_id,)).fetchone()
        media_rows = conn.execute('SELECT file_path FROM project_media WHERE project_id = ?', (project_id,)).fetchall()
        conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        conn.commit()
        conn.close()
        for row in media_rows:
            delete_stored_file(row['file_path'])
        flash(f'Project {project["project_ref"] if project else ""} deleted successfully.', 'success')
        return redirect(url_for('projects'))

    @app.route('/projects/<int:project_id>/media', methods=['POST'])
    @login_required
    def upload_project_media(project_id):
        validate_csrf_form()
        project = get_project_by_id(project_id)
        if project is None:
            abort(404)
        try:
            files = request.files.getlist('media_files')
            category = request.form.get('media_category', 'Other')
            if not files:
                flash('Please select one or more media files.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            save_uploaded_media(project_id, files, category=category)
            flash('Media uploaded successfully.', 'success')
        except ValueError as exc:
            flash(str(exc), 'danger')
        return redirect(url_for('project_detail', project_id=project_id))

    @app.route('/media/<int:media_id>/delete', methods=['POST'])
    @login_required
    def delete_media(media_id):
        validate_csrf_form()
        conn = get_db_connection()
        row = conn.execute('SELECT * FROM project_media WHERE id = ?', (media_id,)).fetchone()
        if row:
            project_id = row['project_id']
            delete_stored_file(row['file_path'])
            conn.execute('DELETE FROM project_media WHERE id = ?', (media_id,))
            conn.commit()
            conn.close()
            flash('Media deleted successfully.', 'success')
            return redirect(url_for('project_detail', project_id=project_id))
        conn.close()
        flash('Media not found.', 'danger')
        return redirect(url_for('projects'))

    @app.route('/showcase-media/<int:media_id>/delete', methods=['POST'])
    @login_required
    def delete_showcase_media(media_id):
        validate_csrf_form()
        conn = get_db_connection()
        row = conn.execute('SELECT file_path, work_category FROM showcase_media WHERE id = ?', (media_id,)).fetchone()
        if row is None:
            conn.close()
            flash('Portfolio photo not found.', 'danger')
            return redirect(url_for('gallery'))

        delete_stored_file(row['file_path'])
        conn.execute('DELETE FROM showcase_media WHERE id = ?', (media_id,))
        conn.commit()
        conn.close()
        flash('Portfolio photo deleted.', 'success')
        return redirect(url_for('gallery', category=row['work_category']))

    @app.route('/category/<category_slug>')
    def category_page(category_slug):
        category_name = next(
            (category for category in CATEGORY_CHOICES if category.lower().replace(' ', '-') == category_slug),
            None,
        )
        if category_name is None:
            abort(404)
        conn = get_db_connection()
        rows = conn.execute(
            '''
            SELECT p.id, p.project_ref, p.title, p.category, p.status
            FROM projects p
            WHERE p.category = ?
            ORDER BY p.created_at DESC
            ''',
            (category_name,),
        ).fetchall()
        conn.close()
        return render_template('projects/category_page.html', category_name=category_name, projects=rows)

    @app.route('/gallery')
    def gallery():
        category = request.args.get('category', 'All')
        media_type = request.args.get('media_type', 'All')
        work_stage = request.args.get('work_stage', 'All')
        q = request.args.get('q', '').strip()

        sql = '''
            SELECT * FROM (
                SELECT m.id, m.project_id, m.media_type, m.category, m.file_name,
                    m.original_name, m.file_path, m.created_at, p.title AS project_title,
                    p.category AS project_category, 0 AS is_showcase
                FROM project_media m
                JOIN projects p ON p.id = m.project_id
                UNION ALL
                SELECT id, NULL AS project_id, media_type, category, file_name,
                    original_name, file_path, created_at, 'Portfolio Photo' AS project_title,
                    work_category AS project_category, 1 AS is_showcase
                FROM showcase_media
            ) AS gallery_media
            WHERE 1=1
        '''
        params = []
        if category != 'All':
            sql += ' AND project_category = ? '
            params.append(category)
        if media_type != 'All':
            sql += ' AND media_type = ? '
            params.append(media_type)
        if work_stage != 'All':
            sql += ' AND category = ? '
            params.append(work_stage)
        if q:
            sql += ' AND (lower(project_title) LIKE lower(?) OR lower(project_category) LIKE lower(?)) '
            params.append(f'%{q}%')
            params.append(f'%{q}%')
        sql += ' ORDER BY created_at DESC'
        conn = get_db_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return render_template('gallery/gallery.html', media=rows, category=category, media_type=media_type, work_stage=work_stage, search=q)

    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        if request.method == 'POST':
            validate_csrf_form()
            if 'new_password' in request.form:
                password = request.form.get('new_password', '').strip()
                if len(password) < 6:
                    flash('Password must be at least 6 characters long.', 'danger')
                else:
                    username = session.get('username', 'admin')
                    conn = get_db_connection()
                    conn.execute('UPDATE admin_users SET password_hash = ? WHERE username = ?', (generate_password_hash(password), username))
                    conn.commit()
                    conn.close()
                    flash('Password updated successfully.', 'success')
            elif 'backup' in request.form:
                return backup_database()
        return render_template('settings.html')

    @app.route('/backup-database', methods=['POST'])
    @login_required
    def backup_database():
        validate_csrf_form()
        if Config.DATABASE_URL or Config.BLOB_STORAGE_ENABLED:
            flash(
                'This deployment stores data in hosted services. Use your database and Vercel Blob provider dashboards to manage backups.',
                'warning',
            )
            return redirect(url_for('settings'))

        backup_dir = INSTANCE_FOLDER / 'backups'
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f'welding_backup_{timestamp}.zip'
        archive_path = backup_dir / archive_name

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(DB_PATH, arcname='database/welding.db')
            for item in UPLOAD_FOLDER.rglob('*'):
                if item.is_file():
                    zip_file.write(item, arcname=str(item.relative_to(BASE_DIR)).replace('\\', '/'))

        flash(f'Backup created successfully: {archive_name}', 'success')
        return redirect(url_for('settings'))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template('413.html', max_upload_size_mb=Config.MAX_UPLOAD_SIZE_MB), 413

    @app.context_processor
    def inject_nav():
        return {'current_user': session.get('username', 'Admin')}

    return app


app = create_app()


if __name__ == '__main__':
    app.run(
        debug=False,
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', '5000')),
    )
