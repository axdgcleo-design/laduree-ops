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
    dr = sum(p['amount'] for p in rows if p['status']=='received' and p['contract_type']=='design')
    er = sum(p['amount'] for p in rows if p['status']=='received' and p['contract_type']=='construction')
    dp = sum(p['amount'] for p in rows if p['status']!='received' and p['contract_type']=='design')
    ep = sum(p['amount'] for p in rows if p['status']!='received' and p['contract_type']=='construction')
    return dict(periods=rows,design_received=dr,eng_received=er,
                design_pending=dp,eng_pending=ep,
                total_received=dr+er,total_pending=dp+ep)

def project_task_counts(pid):
    """單案場的待辦/缺失統計"""
    ph = _ph()
    todo_open   = (fetchone(f"SELECT COUNT(*) as c FROM tasks WHERE project_id={ph} AND type='todo' AND status='open'", (pid,)) or {}).get('c', 0)
    todo_closed = (fetchone(f"SELECT COUNT(*) as c FROM tasks WHERE project_id={ph} AND type='todo' AND status='closed'", (pid,)) or {}).get('c', 0)
    defect_open   = (fetchone(f"SELECT COUNT(*) as c FROM tasks WHERE project_id={ph} AND type='defect' AND status='open'", (pid,)) or {}).get('c', 0)
    defect_closed = (fetchone(f"SELECT COUNT(*) as c FROM tasks WHERE project_id={ph} AND type='defect' AND status='closed'", (pid,)) or {}).get('c', 0)
    return {
        'todo_open': todo_open,
        'todo_closed': todo_closed,
        'todo_total': todo_open + todo_closed,
        'defect_open': defect_open,
        'defect_closed': defect_closed,
        'defect_total': defect_open + defect_closed,
    }

def all_project_task_counts():
    """所有案場的任務統計，回傳 {project_id: counts_dict}"""
    rows = fetchall("""
        SELECT project_id, type, status, COUNT(*) as c
        FROM tasks
        WHERE project_id IS NOT NULL
        GROUP BY project_id, type, status
    """)
    result = {}
    for r in rows:
        pid = r['project_id']
        if pid not in result:
            result[pid] = {'todo_open':0,'todo_closed':0,'defect_open':0,'defect_closed':0}
        key = f"{r['type']}_{r['status']}"
        if key in result[pid]:
            result[pid][key] = r['c']
    for pid, d in result.items():
        d['todo_total'] = d['todo_open'] + d['todo_closed']
        d['defect_total'] = d['defect_open'] + d['defect_closed']
    return result

def _map_status(s):
    return {'進行中':'active','已完工':'completed','暫停':'paused'}.get(s,'active')

def _map_payment(s):
    if not s: return ''
    return {'轉帳':'transfer','現金':'cash','開票':'check'}.get(s, s.lower())

# ── init DB ──────────────────────────────────────────────────────────
def init_db():
    if IS_PG:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE, code TEXT UNIQUE,
            name TEXT NOT NULL, client_name TEXT DEFAULT '', client_tel TEXT DEFAULT '',
            client_email TEXT DEFAULT '', address TEXT DEFAULT '', start_date TEXT DEFAULT '',
            status TEXT DEFAULT 'active', design_contract FLOAT DEFAULT 0,
            design_tax TEXT DEFAULT '未稅', engineering_contract FLOAT DEFAULT 0,
            engineering_tax TEXT DEFAULT '未稅', note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS invoice_periods (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            period_no INTEGER NOT NULL DEFAULT 1, contract_type TEXT DEFAULT 'design',
            label TEXT DEFAULT '', ratio FLOAT DEFAULT 0, amount FLOAT DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', due_date TEXT DEFAULT '',
            payment_method TEXT DEFAULT '', account_last5 TEXT DEFAULT '',
            has_invoice INTEGER DEFAULT 0, invoice_no TEXT DEFAULT '',
            invoice_date TEXT DEFAULT '', received_date TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vendors (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL,
            contact TEXT DEFAULT '', tel TEXT DEFAULT '', category TEXT DEFAULT '',
            bank_name TEXT DEFAULT '', bank_account TEXT DEFAULT '',
            bank_holder TEXT DEFAULT '', note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vendor_contracts (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', category TEXT DEFAULT '',
            amount FLOAT DEFAULT 0, tax_setting TEXT DEFAULT '未稅',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vendor_invoices (
            id SERIAL PRIMARY KEY,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', period_name TEXT DEFAULT '',
            due_date TEXT DEFAULT '', amount FLOAT DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', paid_date TEXT DEFAULT '',
            payment_method TEXT DEFAULT '', paid_account TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vendor_payments (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', category TEXT DEFAULT '',
            period_name TEXT DEFAULT '', date TEXT DEFAULT '',
            amount FLOAT DEFAULT 0, fee FLOAT DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', payment_method TEXT DEFAULT '',
            account_no TEXT DEFAULT '', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', status TEXT DEFAULT '已付',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS company_expenses (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            date TEXT DEFAULT '', category TEXT DEFAULT '', item TEXT DEFAULT '',
            vendor TEXT DEFAULT '', amount FLOAT DEFAULT 0, tax_setting TEXT DEFAULT '含稅',
            payment_method TEXT DEFAULT '', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', recurring TEXT DEFAULT '否',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS extra_works (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            type TEXT DEFAULT '追加', description TEXT DEFAULT '',
            date TEXT DEFAULT '', amount FLOAT DEFAULT 0,
            invoice_no TEXT DEFAULT '', target TEXT DEFAULT '業主',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS pending_payments (
            id SERIAL PRIMARY KEY, legacy_id TEXT UNIQUE,
            due_date TEXT DEFAULT '', type TEXT DEFAULT 'vendor',
            vendor_name TEXT DEFAULT '',
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            amount FLOAT DEFAULT 0, payment_method TEXT DEFAULT '',
            category TEXT DEFAULT '', status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            type TEXT DEFAULT 'todo', title TEXT NOT NULL,
            description TEXT DEFAULT '', priority TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'open', due_date TEXT DEFAULT '',
            image_url TEXT DEFAULT '', source TEXT DEFAULT 'web',
            note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS company_info (
            id INTEGER PRIMARY KEY DEFAULT 1,
            name TEXT DEFAULT '漣一設計有限公司',
            name_en TEXT DEFAULT 'LA DURÉE', tax_id TEXT DEFAULT '',
            address TEXT DEFAULT '', tel TEXT DEFAULT '', email TEXT DEFAULT '',
            bank_name TEXT DEFAULT '', bank_account TEXT DEFAULT '',
            bank_account_name TEXT DEFAULT ''
        );
        INSERT INTO company_info (id) VALUES (1) ON CONFLICT DO NOTHING;
        """)
        conn.commit(); conn.close()
    else:
        import sqlite3
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(os.path.join(BASE_DIR,'data'), exist_ok=True)
        conn = sqlite3.connect(os.path.join(BASE_DIR,'data','ops.db'))
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE, code TEXT UNIQUE,
            name TEXT NOT NULL, client_name TEXT DEFAULT '', client_tel TEXT DEFAULT '',
            client_email TEXT DEFAULT '', address TEXT DEFAULT '', start_date TEXT DEFAULT '',
            status TEXT DEFAULT 'active', design_contract REAL DEFAULT 0,
            design_tax TEXT DEFAULT '未稅', engineering_contract REAL DEFAULT 0,
            engineering_tax TEXT DEFAULT '未稅', note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS invoice_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            period_no INTEGER NOT NULL DEFAULT 1, contract_type TEXT DEFAULT 'design',
            label TEXT DEFAULT '', ratio REAL DEFAULT 0, amount REAL DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', due_date TEXT DEFAULT '',
            payment_method TEXT DEFAULT '', account_last5 TEXT DEFAULT '',
            has_invoice INTEGER DEFAULT 0, invoice_no TEXT DEFAULT '',
            invoice_date TEXT DEFAULT '', received_date TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            contact TEXT DEFAULT '', tel TEXT DEFAULT '', category TEXT DEFAULT '',
            bank_name TEXT DEFAULT '', bank_account TEXT DEFAULT '',
            bank_holder TEXT DEFAULT '', note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS vendor_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', category TEXT DEFAULT '',
            amount REAL DEFAULT 0, tax_setting TEXT DEFAULT '未稅',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS vendor_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', period_name TEXT DEFAULT '',
            due_date TEXT DEFAULT '', amount REAL DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', paid_date TEXT DEFAULT '',
            payment_method TEXT DEFAULT '', paid_account TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS vendor_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            vendor_name TEXT DEFAULT '', category TEXT DEFAULT '',
            period_name TEXT DEFAULT '', date TEXT DEFAULT '',
            amount REAL DEFAULT 0, fee REAL DEFAULT 0,
            tax_setting TEXT DEFAULT '未稅', payment_method TEXT DEFAULT '',
            account_no TEXT DEFAULT '', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', status TEXT DEFAULT '已付',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS company_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            date TEXT DEFAULT '', category TEXT DEFAULT '', item TEXT DEFAULT '',
            vendor TEXT DEFAULT '', amount REAL DEFAULT 0, tax_setting TEXT DEFAULT '含稅',
            payment_method TEXT DEFAULT '', invoice_status TEXT DEFAULT '無發票',
            invoice_no TEXT DEFAULT '', recurring TEXT DEFAULT '否',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS extra_works (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            type TEXT DEFAULT '追加', description TEXT DEFAULT '',
            date TEXT DEFAULT '', amount REAL DEFAULT 0,
            invoice_no TEXT DEFAULT '', target TEXT DEFAULT '業主',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
            due_date TEXT DEFAULT '', type TEXT DEFAULT 'vendor',
            vendor_name TEXT DEFAULT '',
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            amount REAL DEFAULT 0, payment_method TEXT DEFAULT '',
            category TEXT DEFAULT '', status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            type TEXT DEFAULT 'todo', title TEXT NOT NULL,
            description TEXT DEFAULT '', priority TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'open', due_date TEXT DEFAULT '',
            image_url TEXT DEFAULT '', source TEXT DEFAULT 'web',
            note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS company_info (
            id INTEGER PRIMARY KEY DEFAULT 1,
            name TEXT DEFAULT '漣一設計有限公司',
            name_en TEXT DEFAULT 'LA DURÉE', tax_id TEXT DEFAULT '',
            address TEXT DEFAULT '', tel TEXT DEFAULT '', email TEXT DEFAULT '',
            bank_name TEXT DEFAULT '', bank_account TEXT DEFAULT '',
            bank_account_name TEXT DEFAULT ''
        );
        INSERT OR IGNORE INTO company_info (id) VALUES (1);
        """)
        conn.commit(); conn.close()

# 啟動時自動建表（gunicorn 不走 __main__，故在 import 時執行一次；
# CREATE TABLE IF NOT EXISTS 具冪等性，多 worker 併發亦安全）
try:
    init_db()
except Exception as e:
    print(f"init_db error: {e}")

# ── Routes ───────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    projects = fetchall("SELECT * FROM projects ORDER BY created_at DESC")
    stats = {p['id']: project_stats(p['id']) for p in projects}
    task_counts = all_project_task_counts()
    td = sum(p['design_contract'] for p in projects)
    te = sum(p['engineering_contract'] for p in projects)
    tr = sum(stats[p['id']]['total_received'] for p in projects)
    tp = sum(stats[p['id']]['total_pending'] for p in projects)
    return render_template('dashboard.html', projects=projects, stats=stats,
        task_counts=task_counts, fmt=fmt,
        total_design_contract=td, total_eng_contract=te,
        total_received=tr, total_pending=tp)

@app.route('/projects')
def project_list():
    projects = fetchall("SELECT * FROM projects ORDER BY created_at DESC")
    stats = {p['id']: project_stats(p['id']) for p in projects}
    task_counts = all_project_task_counts()
    return render_template('project_list.html', projects=projects,
                           stats=stats, task_counts=task_counts, fmt=fmt)

@app.route('/project/new', methods=['GET','POST'])
def project_new():
    if request.method == 'POST':
        d = request.form
        ph = _ph()
        code = next_code()
        execute(f"""INSERT INTO projects (code,name,client_name,client_tel,client_email,
            address,start_date,status,design_contract,design_tax,
            engineering_contract,engineering_tax,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (code,d['name'],d.get('client_name',''),d.get('client_tel',''),
             d.get('client_email',''),d.get('address',''),d.get('start_date',''),
             d.get('status','active'),float(d.get('design_contract',0) or 0),
             d.get('design_tax','未稅'),float(d.get('engineering_contract',0) or 0),
             d.get('engineering_tax','未稅'),d.get('note','')))
        commit()
        pid = last_insert_id()
        _save_periods(pid, d)
        commit()
        return redirect(url_for('project_detail', pid=pid))
    return render_template('project_form.html', project=None, code=next_code())

@app.route('/project/<int:pid>')
def project_detail(pid):
    ph = _ph()
    project = fetchone(f"SELECT * FROM projects WHERE id={ph}", (pid,))
    if not project: return redirect(url_for('dashboard'))
    project_tasks = fetchall(
        f"SELECT * FROM tasks WHERE project_id={ph} ORDER BY status, due_date, created_at DESC",
        (pid,)
    )
    todos   = [t for t in project_tasks if t['type'] == 'todo']
    defects = [t for t in project_tasks if t['type'] == 'defect']
    return render_template('project_detail.html', project=project,
                           stats=project_stats(pid), fmt=fmt,
                           todos=todos, defects=defects,
                           tcounts=project_task_counts(pid))

@app.route('/project/<int:pid>/edit', methods=['GET','POST'])
def project_edit(pid):
    ph = _ph()
    project = fetchone(f"SELECT * FROM projects WHERE id={ph}", (pid,))
    if not project: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        d = request.form
        execute(f"""UPDATE projects SET name={ph},client_name={ph},client_tel={ph},
            client_email={ph},address={ph},start_date={ph},status={ph},
            design_contract={ph},design_tax={ph},
            engineering_contract={ph},engineering_tax={ph},note={ph} WHERE id={ph}""",
            (d['name'],d.get('client_name',''),d.get('client_tel',''),
             d.get('client_email',''),d.get('address',''),d.get('start_date',''),
             d.get('status','active'),float(d.get('design_contract',0) or 0),
             d.get('design_tax','未稅'),float(d.get('engineering_contract',0) or 0),
             d.get('engineering_tax','未稅'),d.get('note',''),pid))
        commit()
        return redirect(url_for('project_detail', pid=pid))
    existing = fetchall(f"SELECT * FROM invoice_periods WHERE project_id={ph} AND status='pending' ORDER BY contract_type,period_no",(pid,))
    return render_template('project_form.html', project=project,
                           code=project['code'], existing_periods=existing)

@app.route('/project/<int:pid>/delete', methods=['POST'])
def project_delete(pid):
    execute(f"DELETE FROM projects WHERE id={_ph()}", (pid,))
    commit()
    return redirect(url_for('dashboard'))

def _save_periods(pid, d):
    labels = d.getlist('period_label')
    pcts   = d.getlist('period_pct')
    dues   = d.getlist('period_due')
    ctypes = d.getlist('period_ctype')
    da = float(d.get('design_contract',0) or 0)
    ea = float(d.get('engineering_contract',0) or 0)
    counts = {}
    ph = _ph()
    for label,pct,due,ct in zip(labels,pcts,dues,ctypes):
        label = label.strip()
        if not label: continue
        try: pv = float(pct)
        except: pv = 0
        amt = round((da if ct=='design' else ea) * pv / 100)
        counts[ct] = counts.get(ct,0)+1
        execute(f"INSERT INTO invoice_periods (project_id,period_no,contract_type,label,ratio,amount,due_date,status) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},'pending')",
                (pid,counts[ct],ct,label,pv,amt,due))

@app.route('/api/project/<int:pid>/periods', methods=['POST'])
def api_period_add(pid):
    d = request.json; ph = _ph()
    ct = d.get('contract_type','design')
    row = fetchone(f"SELECT COUNT(*) as c FROM invoice_periods WHERE project_id={ph} AND contract_type={ph}",(pid,ct))
    n = row['c'] if row else 0
    execute(f"INSERT INTO invoice_periods (project_id,period_no,contract_type,label,amount,due_date,payment_method,account_last5,has_invoice,invoice_no,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (pid,n+1,ct,d.get('label',''),float(d.get('amount',0)),d.get('due_date',''),
             d.get('payment_method',''),d.get('account_last5',''),
             1 if d.get('has_invoice') else 0,d.get('invoice_no',''),d.get('note','')))
    commit()
    return jsonify({'ok':True})

@app.route('/api/period/<int:iid>', methods=['PATCH'])
def api_period_update(iid):
    d = request.json; ph = _ph()
    fields,vals = [],[]
    for k in ('label','amount','due_date','payment_method','account_last5','has_invoice','invoice_no','invoice_date','received_date','status','note'):
        if k in d: fields.append(f"{k}={ph}"); vals.append(d[k])
    if not fields: return jsonify({'ok':False})
    vals.append(iid)
    execute(f"UPDATE invoice_periods SET {','.join(fields)} WHERE id={ph}", vals)
    commit()
    return jsonify({'ok':True})

@app.route('/api/period/<int:iid>', methods=['DELETE'])
def api_period_delete(iid):
    ph = _ph()
    row = fetchone(f"SELECT project_id,contract_type FROM invoice_periods WHERE id={ph}",(iid,))
    execute(f"DELETE FROM invoice_periods WHERE id={ph}",(iid,))
    if row:
        rows = fetchall(f"SELECT id FROM invoice_periods WHERE project_id={ph} AND contract_type={ph} ORDER BY period_no",(row['project_id'],row['contract_type']))
        for i,r in enumerate(rows):
            execute(f"UPDATE invoice_periods SET period_no={ph} WHERE id={ph}",(i+1,r['id']))
    commit()
    return jsonify({'ok':True})

@app.route('/invoice/<int:iid>/print')
def invoice_print(iid):
    ph = _ph()
    period  = fetchone(f"SELECT * FROM invoice_periods WHERE id={ph}",(iid,))
    if not period: return "not found",404
    project = fetchone(f"SELECT * FROM projects WHERE id={ph}",(period['project_id'],))
    company = fetchone("SELECT * FROM company_info WHERE id=1")
    ct = period['contract_type']
    all_periods = fetchall(f"SELECT * FROM invoice_periods WHERE project_id={ph} AND contract_type={ph} ORDER BY period_no",(project['id'],ct))
    received_sum    = sum(p['amount'] for p in all_periods if p['status']=='received')
    contract_amount = project['design_contract'] if ct=='design' else project['engineering_contract']
    import base64
    logo_b64 = os.environ.get('LOGO_B64','')
    if not IS_PG:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lp = os.path.join(BASE_DIR,'data','logo.png')
        if os.path.exists(lp):
            with open(lp,'rb') as f: logo_b64 = base64.b64encode(f.read()).decode()
    return render_template('invoice_print.html',
        period=period,project=project,company=company,
        all_periods=all_periods,total_periods=len(all_periods),
        received_sum=received_sum,contract_amount=contract_amount,
        logo_b64=logo_b64,fmt=fmt)

@app.route('/tasks')
def tasks():
    ph = _ph()
    pid = request.args.get('project_id')
    tt  = request.args.get('type','all')
    projects = fetchall("SELECT * FROM projects ORDER BY name")
    sql = "SELECT t.*,p.name as project_name FROM tasks t LEFT JOIN projects p ON t.project_id=p.id WHERE 1=1"
    params = []
    if pid: sql+=f" AND t.project_id={ph}"; params.append(pid)
    if tt!='all': sql+=f" AND t.type={ph}"; params.append(tt)
    sql+=" ORDER BY t.status,t.due_date,t.created_at DESC"
    all_tasks = fetchall(sql,params)
    return render_template('tasks.html',
        open_tasks=[t for t in all_tasks if t['status']=='open'],
        closed_tasks=[t for t in all_tasks if t['status']=='closed'],
        projects=projects,task_type=tt,selected_project=pid,fmt=fmt)

@app.route('/api/task', methods=['POST'])
def api_task_add():
    d = request.json; ph = _ph()
    execute(f"INSERT INTO tasks (project_id,type,title,description,priority,due_date,note,source) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (d.get('project_id'),d.get('type','todo'),d.get('title',''),
             d.get('description',''),d.get('priority','normal'),
             d.get('due_date',''),d.get('note',''),d.get('source','web')))
    commit()
    return jsonify({'ok':True})

@app.route('/api/task/<int:tid>', methods=['PATCH'])
def api_task_update(tid):
    d = request.json; ph = _ph()
    fields,vals = [],[]
    for k in ('title','description','priority','status','due_date','note','project_id','type'):
        if k in d: fields.append(f"{k}={ph}"); vals.append(d[k])
    if not fields: return jsonify({'ok':False})
    vals.append(tid)
    execute(f"UPDATE tasks SET {','.join(fields)} WHERE id={ph}",vals)
    commit()
    return jsonify({'ok':True})

@app.route('/api/task/<int:tid>', methods=['DELETE'])
def api_task_delete(tid):
    execute(f"DELETE FROM tasks WHERE id={_ph()}",(tid,))
    commit()
    return jsonify({'ok':True})

@app.route('/finance/vendors')
def finance_vendors():
    vendors  = fetchall("SELECT * FROM vendors ORDER BY name")
    projects = fetchall("SELECT * FROM projects ORDER BY name")
    ph = _ph()
    pending = fetchall(f"SELECT vi.*,v.bank_account,v.bank_holder,v.bank_name,p.name as project_name FROM vendor_invoices vi LEFT JOIN vendors v ON vi.vendor_id=v.id LEFT JOIN projects p ON vi.project_id=p.id WHERE vi.status='pending' ORDER BY vi.due_date")
    paid    = fetchall(f"SELECT vi.*,p.name as project_name FROM vendor_invoices vi LEFT JOIN projects p ON vi.project_id=p.id WHERE vi.status='paid' ORDER BY vi.paid_date DESC LIMIT 50")
    return render_template('finance_vendors.html',vendors=vendors,projects=projects,
        pending=pending,paid=paid,fmt=fmt,now=date.today().isoformat())

@app.route('/api/vendor', methods=['POST'])
def api_vendor_add():
    d = request.json; ph = _ph()
    execute(f"INSERT INTO vendors (name,contact,tel,category,bank_name,bank_account,bank_holder,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (d['name'],d.get('contact',''),d.get('tel',''),d.get('category',''),
             d.get('bank_name',''),d.get('bank_account',''),d.get('bank_holder',''),d.get('note','')))
    commit()
    return jsonify({'ok':True,'id':last_insert_id()})

@app.route('/api/vendor/<int:vid>', methods=['PATCH'])
def api_vendor_update(vid):
    d = request.json; ph = _ph()
    fields,vals = [],[]
    for k in ('name','contact','tel','category','bank_name','bank_account','bank_holder','note'):
        if k in d: fields.append(f"{k}={ph}"); vals.append(d[k])
    if not fields: return jsonify({'ok':False})
    vals.append(vid)
    execute(f"UPDATE vendors SET {','.join(fields)} WHERE id={ph}",vals)
    commit()
    return jsonify({'ok':True})

@app.route('/api/vendor/<int:vid>', methods=['DELETE'])
def api_vendor_delete(vid):
    execute(f"DELETE FROM vendors WHERE id={_ph()}",(vid,))
    commit()
    return jsonify({'ok':True})

@app.route('/api/vendor/<int:vid>', methods=['GET'])
def api_vendor_get(vid):
    v = fetchone(f"SELECT * FROM vendors WHERE id={_ph()}",(vid,))
    return jsonify(v if v else {})

@app.route('/api/vendor-invoice', methods=['POST'])
def api_vendor_invoice_add():
    d = request.json; ph = _ph()
    execute(f"INSERT INTO vendor_invoices (vendor_id,project_id,vendor_name,period_name,due_date,amount,tax_setting,invoice_status,invoice_no,note,status) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},'pending')",
            (d.get('vendor_id'),d.get('project_id'),d.get('vendor_name',''),
             d.get('period_name',''),d.get('due_date',''),float(d.get('amount',0)),
             d.get('tax_setting','未稅'),d.get('invoice_status','無發票'),
             d.get('invoice_no',''),d.get('note','')))
    commit()
    return jsonify({'ok':True})

@app.route('/api/vendor-invoice/<int:iid>/pay', methods=['POST'])
def api_vendor_invoice_pay(iid):
    d = request.json; ph = _ph()
    execute(f"UPDATE vendor_invoices SET status='paid',paid_date={ph},payment_method={ph},paid_account={ph} WHERE id={ph}",
            (d.get('paid_date',''),d.get('payment_method',''),d.get('paid_account',''),iid))
    commit()
    return jsonify({'ok':True})

@app.route('/api/vendor-invoice/<int:iid>', methods=['DELETE'])
def api_vendor_invoice_delete(iid):
    execute(f"DELETE FROM vendor_invoices WHERE id={_ph()}",(iid,))
    commit()
    return jsonify({'ok':True})

@app.route('/finance/expenses')
def finance_expenses():
    expenses = fetchall("SELECT * FROM company_expenses ORDER BY date DESC")
    return render_template('finance_expenses.html',expenses=expenses,fmt=fmt)

@app.route('/api/expense', methods=['POST'])
def api_expense_add():
    d = request.json; ph = _ph()
    execute(f"INSERT INTO company_expenses (date,category,item,vendor,amount,tax_setting,payment_method,invoice_status,invoice_no,recurring,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (d.get('date',''),d.get('category',''),d.get('item',''),d.get('vendor',''),
             float(d.get('amount',0)),d.get('tax_setting','含稅'),d.get('payment_method',''),
             d.get('invoice_status','無發票'),d.get('invoice_no',''),d.get('recurring','否'),d.get('note','')))
    commit()
    return jsonify({'ok':True})

@app.route('/api/expense/<int:eid>', methods=['DELETE'])
def api_expense_delete(eid):
    execute(f"DELETE FROM company_expenses WHERE id={_ph()}",(eid,))
    commit()
    return jsonify({'ok':True})

@app.route('/finance/report')
def finance_report():
    di  = (fetchone("SELECT COALESCE(SUM(amount),0) as v FROM invoice_periods WHERE status='received' AND contract_type='design'") or {}).get('v',0)
    ei  = (fetchone("SELECT COALESCE(SUM(amount),0) as v FROM invoice_periods WHERE status='received' AND contract_type='construction'") or {}).get('v',0)
    ve  = (fetchone("SELECT COALESCE(SUM(amount),0) as v FROM vendor_payments") or {}).get('v',0)
    ce  = (fetchone("SELECT COALESCE(SUM(amount),0) as v FROM company_expenses") or {}).get('v',0)
    ti  = (di or 0)+(ei or 0)
    te  = (ve or 0)+(ce or 0)
    projects = fetchall("SELECT * FROM projects ORDER BY name")
    psl = []
    ph = _ph()
    for p in projects:
        st = project_stats(p['id'])
        vp = (fetchone(f"SELECT COALESCE(SUM(amount),0) as v FROM vendor_payments WHERE project_id={ph}",(p['id'],)) or {}).get('v',0)
        psl.append({**p,**st,'vendor_expense':vp or 0,'profit':st['total_received']-(vp or 0)})
    return render_template('finance_report.html',
        design_income=di or 0,eng_income=ei or 0,
        vendor_expense=ve or 0,company_expense=ce or 0,
        total_income=ti,total_expense=te,profit=ti-te,
        project_stats=psl,fmt=fmt)

@app.route('/api/backup')
def api_backup():
    from flask import Response
    tables = ['projects','invoice_periods','vendors','vendor_contracts',
              'vendor_invoices','vendor_payments','company_expenses',
              'extra_works','pending_payments','tasks','company_info']
    data = {'backup_version':'2.0','backup_date':datetime.now().isoformat()}
    for t in tables:
        try: data[t] = fetchall(f"SELECT * FROM {t}")
        except: data[t] = []
    fn = f"laduree-ops-backup-{datetime.now().strftime('%Y-%m-%d-%H-%M')}.json"
    return Response(json.dumps(data,ensure_ascii=False,indent=2,default=str),
        mimetype='application/json',
        headers={'Content-Disposition':f'attachment; filename="{fn}"'})

@app.route('/api/restore', methods=['POST'])
def api_restore():
    data = request.json
    if data.get('backup_version') == '2.0':
        return _restore_v2(data)
    return api_import_finance()

def _restore_v2(data):
    ph = _ph()
    counts = {}
    for v in data.get('vendors',[]):
        if fetchone(f"SELECT id FROM vendors WHERE id={ph}",(v['id'],)): continue
        execute(f"INSERT INTO vendors (id,name,contact,tel,category,bank_name,bank_account,bank_holder,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (v['id'],v.get('name',''),v.get('contact',''),v.get('tel',''),v.get('category',''),v.get('bank_name',''),v.get('bank_account',''),v.get('bank_holder',''),v.get('note','')))
        counts['vendors'] = counts.get('vendors',0)+1
    for p in data.get('projects',[]):
        if fetchone(f"SELECT id FROM projects WHERE id={ph}",(p['id'],)): continue
        execute(f"INSERT INTO projects (id,legacy_id,code,name,client_name,client_tel,client_email,address,start_date,status,design_contract,design_tax,engineering_contract,engineering_tax,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (p['id'],p.get('legacy_id'),p.get('code',''),p.get('name',''),p.get('client_name',''),p.get('client_tel',''),p.get('client_email',''),p.get('address',''),p.get('start_date',''),p.get('status','active'),p.get('design_contract',0),p.get('design_tax','未稅'),p.get('engineering_contract',0),p.get('engineering_tax','未稅'),p.get('note','')))
        counts['projects'] = counts.get('projects',0)+1
    for ip in data.get('invoice_periods',[]):
        if fetchone(f"SELECT id FROM invoice_periods WHERE id={ph}",(ip['id'],)): continue
        execute(f"INSERT INTO invoice_periods (id,project_id,period_no,contract_type,label,ratio,amount,due_date,payment_method,account_last5,has_invoice,invoice_no,invoice_date,received_date,status,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (ip['id'],ip.get('project_id'),ip.get('period_no',1),ip.get('contract_type','design'),ip.get('label',''),ip.get('ratio',0),ip.get('amount',0),ip.get('due_date',''),ip.get('payment_method',''),ip.get('account_last5',''),ip.get('has_invoice',0),ip.get('invoice_no',''),ip.get('invoice_date',''),ip.get('received_date',''),ip.get('status','pending'),ip.get('note','')))
        counts['invoice_periods'] = counts.get('invoice_periods',0)+1
    for vi in data.get('vendor_invoices',[]):
        if fetchone(f"SELECT id FROM vendor_invoices WHERE id={ph}",(vi['id'],)): continue
        execute(f"INSERT INTO vendor_invoices (id,vendor_id,project_id,vendor_name,period_name,due_date,amount,tax_setting,invoice_status,invoice_no,note,status,paid_date,payment_method) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (vi['id'],vi.get('vendor_id'),vi.get('project_id'),vi.get('vendor_name',''),vi.get('period_name',''),vi.get('due_date',''),vi.get('amount',0),vi.get('tax_setting','未稅'),vi.get('invoice_status','無發票'),vi.get('invoice_no',''),vi.get('note',''),vi.get('status','pending'),vi.get('paid_date',''),vi.get('payment_method','')))
        counts['vendor_invoices'] = counts.get('vendor_invoices',0)+1
    for vp in data.get('vendor_payments',[]):
        if fetchone(f"SELECT id FROM vendor_payments WHERE id={ph}",(vp['id'],)): continue
        execute(f"INSERT INTO vendor_payments (id,legacy_id,project_id,vendor_name,category,period_name,date,amount,fee,tax_setting,payment_method,account_no,invoice_status,invoice_no,status,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (vp['id'],vp.get('legacy_id'),vp.get('project_id'),vp.get('vendor_name',''),vp.get('category',''),vp.get('period_name',''),vp.get('date',''),vp.get('amount',0),vp.get('fee',0),vp.get('tax_setting','未稅'),vp.get('payment_method',''),vp.get('account_no',''),vp.get('invoice_status','無發票'),vp.get('invoice_no',''),vp.get('status','已付'),vp.get('note','')))
        counts['vendor_payments'] = counts.get('vendor_payments',0)+1
    for ce in data.get('company_expenses',[]):
        if fetchone(f"SELECT id FROM company_expenses WHERE id={ph}",(ce['id'],)): continue
        execute(f"INSERT INTO company_expenses (id,legacy_id,date,category,item,vendor,amount,tax_setting,payment_method,invoice_status,invoice_no,recurring,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (ce['id'],ce.get('legacy_id'),ce.get('date',''),ce.get('category',''),ce.get('item',''),ce.get('vendor',''),ce.get('amount',0),ce.get('tax_setting','含稅'),ce.get('payment_method',''),ce.get('invoice_status','無發票'),ce.get('invoice_no',''),ce.get('recurring','否'),ce.get('note','')))
        counts['company_expenses'] = counts.get('company_expenses',0)+1
    commit()
    return jsonify({'ok':True,'restored':counts})

@app.route('/api/import', methods=['POST'])
def api_import_finance():
    data = request.json; ph = _ph()
    imported = {'projects':0,'periods':0}
    for p in data.get('projects',[]):
        if fetchone(f"SELECT id FROM projects WHERE legacy_id={ph}",(p['id'],)): continue
        code = next_code()
        execute(f"INSERT INTO projects (legacy_id,code,name,client_name,start_date,status,design_contract,design_tax,engineering_contract,engineering_tax,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (p['id'],code,p.get('name',''),p.get('client',''),p.get('startDate',''),_map_status(p.get('status','進行中')),p.get('designContract',0),p.get('designTaxSetting','未稅'),p.get('engineeringContract',0),p.get('engineeringTaxSetting','未稅'),p.get('note','')))
        imported['projects']+=1
    commit()
    pid_map = {r['legacy_id']:r['id'] for r in fetchall("SELECT id,legacy_id FROM projects WHERE legacy_id IS NOT NULL")}
    counts = {}
    for p in data.get('periods',[]):
        if fetchone(f"SELECT id FROM invoice_periods WHERE legacy_id={ph}",(p['id'],)): continue
        pid = pid_map.get(p.get('projectId'))
        if not pid: continue
        ct = 'design' if p.get('contractType','')=='設計費' else 'construction'
        k = (pid,ct); counts[k]=counts.get(k,0)+1
        execute(f"INSERT INTO invoice_periods (legacy_id,project_id,period_no,contract_type,label,ratio,amount,tax_setting,due_date,payment_method,has_invoice,invoice_no,status,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (p['id'],pid,counts[k],ct,p.get('periodName',''),p.get('ratio',0),p.get('amount',0),p.get('taxSetting','未稅'),p.get('dueDate',''),_map_payment(p.get('paymentMethod','')),1 if p.get('invoice','無')!='無' else 0,p.get('invoiceNo',''),'received' if p.get('status','')=='已收' else 'pending',p.get('note','')))
        imported['periods']+=1
    commit()
    return jsonify({'ok':True,'imported':imported})

@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    import requests as req
    data = request.json
    if not data: return 'ok'
    msg = data.get('message',{})
    chat_id = msg.get('chat',{}).get('id')
    text = msg.get('text','')
    photo = msg.get('photo')
    if not chat_id: return 'ok'

    def reply(txt):
        req.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                 json={'chat_id':chat_id,'text':txt,'parse_mode':'HTML'})

    if photo and ANTHROPIC_KEY:
        file_id = photo[-1]['file_id']
        fi = req.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}').json()
        fp = fi['result']['file_path']
        img = req.get(f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fp}').content
        import anthropic, base64
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(model='claude-sonnet-4-6',max_tokens=300,
            messages=[{'role':'user','content':[
                {'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(img).decode()}},
                {'type':'text','text':'這是發票或收據，只回傳JSON: {"amount":數字,"vendor":"廠商","date":"日期"}'}
            ]}])
        try:
            r = json.loads(resp.content[0].text)
            reply(f"📷 辨識結果：\n💰 NT$ {r.get('amount',0):,}\n🏪 {r.get('vendor','')}\n📅 {r.get('date','')}\n\n確認後輸入：/pay {r.get('amount',0)} {r.get('vendor','')}")
        except:
            reply("照片收到，請手動輸入：\n/pay 金額 廠商\n/todo 待辦\n/defect 缺失")
        return 'ok'

    ph = _ph()
    if text.startswith('/pay'):
        parts = text.split(' ',3)
        if len(parts)>=3:
            try:
                amt = float(parts[1].replace(',',''))
                vendor = parts[2]
                note = parts[3] if len(parts)>3 else ''
                execute(f"INSERT INTO vendor_invoices (vendor_name,amount,note,status) VALUES ({ph},{ph},{ph},'pending')",(vendor,amt,note))
                commit()
                reply(f"✅ 待付款已新增\n廠商：{vendor}\n金額：NT$ {amt:,.0f}")
            except: reply("格式：/pay 金額 廠商名稱")
        else: reply("格式：/pay 金額 廠商名稱")
    elif text.startswith('/todo'):
        title = text[5:].strip()
        if title:
            execute(f"INSERT INTO tasks (title,type,status,source) VALUES ({ph},'todo','open','telegram')",(title,))
            commit()
            reply(f"✅ 待辦：{title}")
        else: reply("格式：/todo 待辦內容")
    elif text.startswith('/defect'):
        title = text[7:].strip()
        if title:
            execute(f"INSERT INTO tasks (title,type,status,source) VALUES ({ph},'defect','open','telegram')",(title,))
            commit()
            reply(f"🔴 缺失：{title}")
        else: reply("格式：/defect 缺失描述")
    else:
        reply("/pay 金額 廠商\n/todo 待辦\n/defect 缺失\n直接傳照片辨識發票")
    return 'ok'

@app.route('/api/set-webhook', methods=['POST'])
def set_webhook():
    import requests as req
    base = request.json.get('url') or request.host_url.rstrip('/')
    r = req.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook',json={'url':f'{base}/webhook/telegram'})
    return jsonify(r.json())

@app.route('/settings', methods=['GET','POST'])
def settings():
    ph = _ph()
    if request.method == 'POST':
        d = request.form
        execute(f"UPDATE company_info SET name={ph},name_en={ph},tax_id={ph},address={ph},tel={ph},email={ph},bank_name={ph},bank_account={ph},bank_account_name={ph} WHERE id=1",
                (d.get('name','漣一設計有限公司'),d.get('name_en','LA DURÉE'),d.get('tax_id',''),d.get('address',''),d.get('tel',''),d.get('email',''),d.get('bank_name',''),d.get('bank_account',''),d.get('bank_account_name','')))
        commit()
        if not IS_PG and 'logo' in request.files:
            f = request.files['logo']
            if f and f.filename:
                BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                f.save(os.path.join(BASE_DIR,'data','logo.png'))
        return redirect(url_for('settings'))
    company = fetchone("SELECT * FROM company_info WHERE id=1") or {}
    import base64
    logo_b64 = os.environ.get('LOGO_B64','')
    if not IS_PG:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lp = os.path.join(BASE_DIR,'data','logo.png')
        if os.path.exists(lp):
            with open(lp,'rb') as f: logo_b64 = base64.b64encode(f.read()).decode()
    webhook_url = request.host_url.rstrip('/')+'/webhook/telegram'
    return render_template('settings.html',company=company,logo_b64=logo_b64,webhook_url=webhook_url)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5006)),debug=False)
