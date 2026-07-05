import os, json
from flask import Flask, render_template, request, jsonify, redirect, url_for, g
from datetime import datetime, date

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL', '')
IS_PG = 'postgres' in DATABASE_URL

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
ANTHROPIC_KEY  = os.environ.get('ANTHROPIC_KEY', '')

# ── DB helpers ───────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        if IS_PG:
            import psycopg2, psycopg2.extras
            g.db = psycopg2.connect(DATABASE_URL)
            g.db_type = 'pg'
        else:
            import sqlite3
            BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
            conn = sqlite3.connect(os.path.join(BASE_DIR, 'data', 'ops.db'))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            g.db = conn
            g.db_type = 'sqlite'
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        try: db.close()
        except: pass

def _ph(): return '%s' if IS_PG else '?'

def fetchall(sql, params=()):
    get_db()
    if g.db_type == 'pg':
        import psycopg2.extras
        s = sql.replace('?','%s')
        cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(s, params)
        return [dict(r) for r in cur.fetchall()]
    return [dict(r) for r in g.db.execute(sql, params).fetchall()]

def fetchone(sql, params=()):
    rows = fetchall(sql, params)
    return rows[0] if rows else None

def execute(sql, params=()):
    get_db()
    if g.db_type == 'pg':
        s = sql.replace('?','%s').replace("datetime('now','localtime')",'NOW()').replace("datetime('now')",'NOW()')
        cur = g.db.cursor()
        cur.execute(s, params)
        return cur
    return g.db.execute(sql, params)

def commit(): get_db().commit()

def last_insert_id():
    get_db()
    if g.db_type == 'pg':
        row = fetchone("SELECT lastval() as id")
        return row['id'] if row else None
    return fetchone("SELECT last_insert_rowid() as id")['id']

def fmt(n):
    try: return f'{float(n):,.0f}'
    except: return '0'

def next_code():
    row = fetchone("SELECT code FROM projects WHERE code LIKE 'P-%' ORDER BY id DESC LIMIT 1")
    if not row: return 'P-001'
    try: n = int(row['code'].split('-')[1]) + 1
    except: n = 1
    return f'P-{n:03d}'

def project_stats(pid):
    ph = _ph()
    rows = fetchall(f"SELECT * FROM invoice_periods WHERE project_id={ph} ORDER BY contract_type,period_no", (pid,))
    dr = sum
