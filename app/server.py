import os, sqlite3, json
from flask import Flask, render_template, request, jsonify, redirect, url_for, g

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'ops.db')

app = Flask(__name__)

# ── DB ──────────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    -- 案場（一個案場同時有設計費＋工程費合約）
    CREATE TABLE IF NOT EXISTS projects (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id             TEXT UNIQUE,
        code                  TEXT UNIQUE,
        name                  TEXT NOT NULL,
        client_name           TEXT DEFAULT '',
        client_tel            TEXT DEFAULT '',
        client_email          TEXT DEFAULT '',
        address               TEXT DEFAULT '',
        start_date            TEXT DEFAULT '',
        status                TEXT DEFAULT 'active',
        design_contract       REAL DEFAULT 0,
        design_tax            TEXT DEFAULT '未稅',
        engineering_contract  REAL DEFAULT 0,
        engineering_tax       TEXT DEFAULT '未稅',
        note                  TEXT DEFAULT '',
        created_at            TEXT DEFAULT (datetime('now','localtime')),
        updated_at            TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 業主請款（設計費或工程費）
    CREATE TABLE IF NOT EXISTS invoice_periods (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id       TEXT UNIQUE,
        project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        period_no       INTEGER NOT NULL DEFAULT 1,
        contract_type   TEXT NOT NULL DEFAULT 'design',
        label           TEXT DEFAULT '',
        ratio           REAL DEFAULT 0,
        amount          REAL DEFAULT 0,
        tax_setting     TEXT DEFAULT '未稅',
        due_date        TEXT DEFAULT '',
        payment_method  TEXT DEFAULT '',
        account_last5   TEXT DEFAULT '',
        has_invoice     INTEGER DEFAULT 0,
        invoice_no      TEXT DEFAULT '',
        invoice_date    TEXT DEFAULT '',
        received_date   TEXT DEFAULT '',
        status          TEXT DEFAULT 'pending',
        note            TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        updated_at      TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 廠商主檔
    CREATE TABLE IF NOT EXISTS vendors (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        contact         TEXT DEFAULT '',
        tel             TEXT DEFAULT '',
        category        TEXT DEFAULT '',
        bank_name       TEXT DEFAULT '',
        bank_account    TEXT DEFAULT '',
        bank_holder     TEXT DEFAULT '',
        note            TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 廠商合約
    CREATE TABLE IF NOT EXISTS vendor_contracts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id       TEXT UNIQUE,
        vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
        project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        vendor_name     TEXT DEFAULT '',
        category        TEXT DEFAULT '',
        amount          REAL DEFAULT 0,
        tax_setting     TEXT DEFAULT '未稅',
        note            TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 廠商請款單（待付→已付）
    CREATE TABLE IF NOT EXISTS vendor_invoices (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
        vendor_contract_id INTEGER REFERENCES vendor_contracts(id) ON DELETE SET NULL,
        project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        vendor_name     TEXT DEFAULT '',
        period_name     TEXT DEFAULT '',
        due_date        TEXT DEFAULT '',
        amount          REAL DEFAULT 0,
        tax_setting     TEXT DEFAULT '未稅',
        invoice_status  TEXT DEFAULT '無發票',
        invoice_no      TEXT DEFAULT '',
        attachment      TEXT DEFAULT '',
        note            TEXT DEFAULT '',
        status          TEXT DEFAULT 'pending',
        paid_date       TEXT DEFAULT '',
        payment_method  TEXT DEFAULT '',
        paid_account    TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 廠商付款（已付紀錄）
    CREATE TABLE IF NOT EXISTS vendor_payments (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id           TEXT UNIQUE,
        vendor_id           INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
        vendor_contract_id  INTEGER REFERENCES vendor_contracts(id) ON DELETE SET NULL,
        project_id          INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        vendor_name         TEXT DEFAULT '',
        category            TEXT DEFAULT '',
        period_name         TEXT DEFAULT '',
        date                TEXT DEFAULT '',
        amount              REAL DEFAULT 0,
        fee                 REAL DEFAULT 0,
        tax_setting         TEXT DEFAULT '未稅',
        payment_method      TEXT DEFAULT '',
        account_no          TEXT DEFAULT '',
        invoice_status      TEXT DEFAULT '無發票',
        invoice_no          TEXT DEFAULT '',
        status              TEXT DEFAULT '已付',
        note                TEXT DEFAULT '',
        created_at          TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 公司支出
    CREATE TABLE IF NOT EXISTS company_expenses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id       TEXT UNIQUE,
        date            TEXT DEFAULT '',
        category        TEXT DEFAULT '',
        item            TEXT DEFAULT '',
        vendor          TEXT DEFAULT '',
        amount          REAL DEFAULT 0,
        tax_setting     TEXT DEFAULT '含稅',
        payment_method  TEXT DEFAULT '',
        invoice_status  TEXT DEFAULT '無發票',
        invoice_no      TEXT DEFAULT '',
        recurring       TEXT DEFAULT '否',
        note            TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 追加工程
    CREATE TABLE IF NOT EXISTS extra_works (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id   TEXT UNIQUE,
        project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        type        TEXT DEFAULT '追加',
        description TEXT DEFAULT '',
        date        TEXT DEFAULT '',
        amount      REAL DEFAULT 0,
        invoice_no  TEXT DEFAULT '',
        target      TEXT DEFAULT '業主',
        note        TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 待付款
    CREATE TABLE IF NOT EXISTS pending_payments (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id           TEXT UNIQUE,
        due_date            TEXT DEFAULT '',
        type                TEXT DEFAULT 'vendor',
        vendor_name         TEXT DEFAULT '',
        project_id          INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        amount              REAL DEFAULT 0,
        payment_method      TEXT DEFAULT '',
        category            TEXT DEFAULT '',
        status              TEXT DEFAULT 'pending',
        note                TEXT DEFAULT '',
        created_at          TEXT DEFAULT (datetime('now','localtime'))
    );

    -- 公司資訊
    CREATE TABLE IF NOT EXISTS company_info (
        id                  INTEGER PRIMARY KEY DEFAULT 1,
        name                TEXT DEFAULT '漣一設計有限公司',
        name_en             TEXT DEFAULT 'LA DURÉE',
        tax_id              TEXT DEFAULT '',
        address             TEXT DEFAULT '',
        tel                 TEXT DEFAULT '',
        email               TEXT DEFAULT '',
        bank_name           TEXT DEFAULT '',
        bank_account        TEXT DEFAULT '',
        bank_account_name   TEXT DEFAULT ''
    );
    INSERT OR IGNORE INTO company_info (id) VALUES (1);
    """)
    db.commit()
    db.close()

# ── helpers ──────────────────────────────────────────────────────────
def fmt(n):
    return f'{n:,.0f}'

def next_code(db):
    row = db.execute("SELECT code FROM projects WHERE code LIKE 'P-%' ORDER BY id DESC LIMIT 1").fetchone()
    if not row: return 'P-001'
    try: n = int(row['code'].split('-')[1]) + 1
    except: n = 1
    return f'P-{n:03d}'

def project_stats(db, pid):
    rows = db.execute(
        "SELECT * FROM invoice_periods WHERE project_id=? ORDER BY contract_type, period_no", (pid,)
    ).fetchall()
    periods = [dict(r) for r in rows]
    design_received = sum(p['amount'] for p in periods if p['status']=='received' and p['contract_type']=='design')
    eng_received    = sum(p['amount'] for p in periods if p['status']=='received' and p['contract_type']=='construction')
    design_pending  = sum(p['amount'] for p in periods if p['status']!='received' and p['contract_type']=='design')
    eng_pending     = sum(p['amount'] for p in periods if p['status']!='received' and p['contract_type']=='construction')
    return dict(
        periods=periods,
        design_received=design_received, eng_received=eng_received,
        design_pending=design_pending, eng_pending=eng_pending,
        total_received=design_received+eng_received,
        total_pending=design_pending+eng_pending
    )

# ── 匯入備份 ──────────────────────────────────────────────────────────
@app.route('/api/import', methods=['POST'])
def api_import():
    db = get_db()
    data = request.json
    imported = {'projects':0,'periods':0,'vendor_payments':0,'company_expenses':0,'extra_works':0,'pending_payments':0}

    # --- projects ---
    for p in data.get('projects', []):
        existing = db.execute("SELECT id FROM projects WHERE legacy_id=?", (p['id'],)).fetchone()
        if existing: continue
        code = next_code(db)
        db.execute("""
            INSERT OR IGNORE INTO projects
                (legacy_id,code,name,client_name,address,start_date,status,
                 design_contract,design_tax,engineering_contract,engineering_tax,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (p['id'], code, p.get('name',''), p.get('client',''),
              p.get('note','') if 'note' in p else '',
              p.get('startDate',''), _map_status(p.get('status','進行中')),
              p.get('designContract',0), p.get('designTaxSetting','未稅'),
              p.get('engineeringContract',0), p.get('engineeringTaxSetting','未稅'),
              p.get('note','')))
        imported['projects'] += 1

    db.commit()

    # build legacy_id -> id map
    pid_map = {r['legacy_id']: r['id'] for r in
               db.execute("SELECT id, legacy_id FROM projects WHERE legacy_id IS NOT NULL")}

    # --- periods ---
    period_counts = {}
    for p in data.get('periods', []):
        if db.execute("SELECT id FROM invoice_periods WHERE legacy_id=?", (p['id'],)).fetchone(): continue
        pid = pid_map.get(p.get('projectId'))
        if not pid: continue
        ct = 'design' if p.get('contractType','') == '設計費' else 'construction'
        key = (pid, ct)
        period_counts[key] = period_counts.get(key, 0) + 1
        db.execute("""
            INSERT OR IGNORE INTO invoice_periods
                (legacy_id,project_id,period_no,contract_type,label,ratio,amount,
                 tax_setting,due_date,payment_method,account_last5,
                 has_invoice,invoice_no,status,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (p['id'], pid, period_counts[key], ct,
              p.get('periodName',''), p.get('ratio',0), p.get('amount',0),
              p.get('taxSetting','未稅'), p.get('dueDate',''),
              _map_payment(p.get('paymentMethod','')),
              p.get('accountNo','')[-5:] if p.get('accountNo') else '',
              1 if p.get('invoice','無') != '無' else 0,
              p.get('invoiceNo',''),
              'received' if p.get('status','') == '已收' else 'pending',
              p.get('note','')))
        imported['periods'] += 1

    db.commit()

    # build vc legacy map
    vc_map = {}
    for vc in data.get('vendor-contracts', []):
        pid = pid_map.get(vc.get('projectId'))
        existing = db.execute("SELECT id FROM vendor_contracts WHERE legacy_id=?", (vc['id'],)).fetchone()
        if existing:
            vc_map[vc['id']] = existing['id']
            continue
        db.execute("""
            INSERT OR IGNORE INTO vendor_contracts
                (legacy_id,project_id,vendor_name,category,amount,tax_setting,note)
            VALUES (?,?,?,?,?,?,?)
        """, (vc['id'], pid, vc.get('vendorName',''), vc.get('category',''),
              vc.get('amount',0), vc.get('taxSetting','未稅'), vc.get('note','')))
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        vc_map[vc['id']] = new_id

    db.commit()

    # --- vendor payments ---
    for vp in data.get('vendor-payments', []):
        if db.execute("SELECT id FROM vendor_payments WHERE legacy_id=?", (vp['id'],)).fetchone(): continue
        pid  = pid_map.get(vp.get('projectId'))
        vcid = vc_map.get(vp.get('vendorContractId'))
        db.execute("""
            INSERT OR IGNORE INTO vendor_payments
                (legacy_id,vendor_contract_id,project_id,vendor_name,category,
                 period_name,date,amount,fee,tax_setting,payment_method,
                 account_no,invoice_status,invoice_no,status,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (vp['id'], vcid, pid,
              vp.get('vendorName',''), vp.get('category',''),
              vp.get('periodName',''), vp.get('date',''),
              vp.get('amount',0), vp.get('fee',0),
              vp.get('taxSetting','未稅'), _map_payment(vp.get('paymentMethod','')),
              vp.get('accountNo',''), vp.get('invoiceStatus','無發票'),
              vp.get('invoiceNo',''),
              'paid' if vp.get('status','') == '已付' else 'pending',
              vp.get('note','')))
        imported['vendor_payments'] += 1

    # --- company expenses ---
    for ce in data.get('company-expenses', []):
        if db.execute("SELECT id FROM company_expenses WHERE legacy_id=?", (ce['id'],)).fetchone(): continue
        db.execute("""
            INSERT OR IGNORE INTO company_expenses
                (legacy_id,date,category,item,vendor,amount,tax_setting,
                 payment_method,invoice_status,invoice_no,recurring,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ce['id'], ce.get('date',''), ce.get('category',''), ce.get('item',''),
              ce.get('vendor',''), ce.get('amount',0), ce.get('taxSetting','含稅'),
              _map_payment(ce.get('paymentMethod','')),
              ce.get('invoiceStatus','無發票'), ce.get('invoiceNo',''),
              ce.get('recurring','否'), ce.get('note','')))
        imported['company_expenses'] += 1

    # --- extra works ---
    for ew in data.get('extra-works', []):
        if db.execute("SELECT id FROM extra_works WHERE legacy_id=?", (ew['id'],)).fetchone(): continue
        pid = pid_map.get(ew.get('projectId'))
        db.execute("""
            INSERT OR IGNORE INTO extra_works
                (legacy_id,project_id,type,description,date,amount,invoice_no,target,note)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (ew['id'], pid, ew.get('type','追加'), ew.get('description',''),
              ew.get('date',''), ew.get('amount',0),
              ew.get('invoiceNo',''), ew.get('target','業主'), ew.get('note','')))
        imported['extra_works'] += 1

    # --- pending payments ---
    for pp in data.get('pending-payments', []):
        if db.execute("SELECT id FROM pending_payments WHERE legacy_id=?", (pp['id'],)).fetchone(): continue
        pid = pid_map.get(pp.get('projectId'))
        db.execute("""
            INSERT OR IGNORE INTO pending_payments
                (legacy_id,due_date,type,vendor_name,project_id,amount,payment_method,category,note)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (pp['id'], pp.get('dueDate',''), pp.get('type','vendor'),
              pp.get('vendorName',''), pid, pp.get('amount',0),
              _map_payment(pp.get('paymentMethod','')),
              pp.get('category',''), pp.get('note','')))
        imported['pending_payments'] += 1

    db.commit()
    return jsonify({'ok': True, 'imported': imported})

def _map_status(s):
    return {'進行中':'active','已完工':'completed','暫停':'paused'}.get(s, 'active')

def _map_payment(s):
    return {'轉帳':'transfer','現金':'cash','開票':'check'}.get(s, s.lower() if s else '')

# ── Dashboard ─────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    db = get_db()
    projects = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY created_at DESC")]
    stats = {p['id']: project_stats(db, p['id']) for p in projects}

    total_design_contract = sum(p['design_contract'] for p in projects)
    total_eng_contract    = sum(p['engineering_contract'] for p in projects)
    total_received        = sum(stats[p['id']]['total_received'] for p in projects)
    total_pending         = sum(stats[p['id']]['total_pending'] for p in projects)

    return render_template('dashboard.html',
        projects=projects, stats=stats, fmt=fmt,
        total_design_contract=total_design_contract,
        total_eng_contract=total_eng_contract,
        total_received=total_received,
        total_pending=total_pending)

# ── Projects ──────────────────────────────────────────────────────────
@app.route('/projects')
def project_list():
    db = get_db()
    projects = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY created_at DESC")]
    stats = {p['id']: project_stats(db, p['id']) for p in projects}
    return render_template('project_list.html', projects=projects, stats=stats, fmt=fmt)

@app.route('/project/new', methods=['GET','POST'])
def project_new():
    db = get_db()
    if request.method == 'POST':
        d = request.form
        code = next_code(db)
        db.execute("""
            INSERT INTO projects (code,name,client_name,client_tel,client_email,
                address,start_date,status,design_contract,design_tax,
                engineering_contract,engineering_tax,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (code, d['name'], d.get('client_name',''), d.get('client_tel',''),
              d.get('client_email',''), d.get('address',''), d.get('start_date',''),
              d.get('status','active'),
              float(d.get('design_contract',0) or 0), d.get('design_tax','未稅'),
              float(d.get('engineering_contract',0) or 0), d.get('engineering_tax','未稅'),
              d.get('note','')))
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        _save_periods(db, pid, d)
        db.commit()
        return redirect(url_for('project_detail', pid=pid))
    return render_template('project_form.html', project=None, code=next_code(db))

@app.route('/project/<int:pid>')
def project_detail(pid):
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not project: return redirect(url_for('dashboard'))
    project = dict(project)
    st = project_stats(db, pid)
    return render_template('project_detail.html', project=project, stats=st, fmt=fmt)

@app.route('/project/<int:pid>/edit', methods=['GET','POST'])
def project_edit(pid):
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not project: return redirect(url_for('dashboard'))
    project = dict(project)
    if request.method == 'POST':
        d = request.form
        db.execute("""
            UPDATE projects SET name=?,client_name=?,client_tel=?,client_email=?,
                address=?,start_date=?,status=?,
                design_contract=?,design_tax=?,
                engineering_contract=?,engineering_tax=?,note=?,
                updated_at=datetime('now','localtime')
            WHERE id=?
        """, (d['name'], d.get('client_name',''), d.get('client_tel',''),
              d.get('client_email',''), d.get('address',''), d.get('start_date',''),
              d.get('status','active'),
              float(d.get('design_contract',0) or 0), d.get('design_tax','未稅'),
              float(d.get('engineering_contract',0) or 0), d.get('engineering_tax','未稅'),
              d.get('note',''), pid))
        db.commit()
        return redirect(url_for('project_detail', pid=pid))
    existing = db.execute(
        "SELECT * FROM invoice_periods WHERE project_id=? AND status='pending' ORDER BY contract_type,period_no",
        (pid,)
    ).fetchall()
    return render_template('project_form.html', project=project, code=project['code'],
                           existing_periods=[dict(r) for r in existing])

@app.route('/project/<int:pid>/delete', methods=['POST'])
def project_delete(pid):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    db.commit()
    return redirect(url_for('dashboard'))

def _save_periods(db, pid, d):
    labels = d.getlist('period_label')
    pcts   = d.getlist('period_pct')
    dues   = d.getlist('period_due')
    ctypes = d.getlist('period_ctype')
    amounts_design = float(d.get('design_contract',0) or 0)
    amounts_eng    = float(d.get('engineering_contract',0) or 0)
    counts = {}
    for label, pct, due, ct in zip(labels, pcts, dues, ctypes):
        label = label.strip()
        if not label: continue
        try: pct_val = float(pct)
        except: pct_val = 0
        base = amounts_design if ct == 'design' else amounts_eng
        amount = round(base * pct_val / 100)
        counts[ct] = counts.get(ct, 0) + 1
        db.execute("""
            INSERT INTO invoice_periods
                (project_id,period_no,contract_type,label,ratio,amount,due_date,status)
            VALUES (?,?,?,?,?,?,?,'pending')
        """, (pid, counts[ct], ct, label, pct_val, amount, due))

# ── API: periods ──────────────────────────────────────────────────────
@app.route('/api/project/<int:pid>/periods', methods=['POST'])
def api_period_add(pid):
    db = get_db()
    d = request.json
    ct = d.get('contract_type', 'design')
    n = db.execute(
        "SELECT COUNT(*) as c FROM invoice_periods WHERE project_id=? AND contract_type=?", (pid, ct)
    ).fetchone()['c']
    db.execute("""
        INSERT INTO invoice_periods
            (project_id,period_no,contract_type,label,amount,due_date,
             payment_method,account_last5,has_invoice,invoice_no,note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (pid, n+1, ct, d.get('label',''), float(d.get('amount',0)),
          d.get('due_date',''), d.get('payment_method',''),
          d.get('account_last5',''), 1 if d.get('has_invoice') else 0,
          d.get('invoice_no',''), d.get('note','')))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/period/<int:iid>', methods=['PATCH'])
def api_period_update(iid):
    db = get_db()
    d = request.json
    fields, vals = [], []
    for k in ('label','amount','due_date','payment_method','account_last5',
              'has_invoice','invoice_no','invoice_date','received_date','status','note'):
        if k in d:
            fields.append(f"{k}=?")
            vals.append(d[k])
    if not fields: return jsonify({'ok': False})
    vals.append(iid)
    db.execute(f"UPDATE invoice_periods SET {','.join(fields)},updated_at=datetime('now','localtime') WHERE id=?", vals)
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/period/<int:iid>', methods=['DELETE'])
def api_period_delete(iid):
    db = get_db()
    row = db.execute("SELECT project_id, contract_type FROM invoice_periods WHERE id=?", (iid,)).fetchone()
    db.execute("DELETE FROM invoice_periods WHERE id=?", (iid,))
    if row:
        rows = db.execute(
            "SELECT id FROM invoice_periods WHERE project_id=? AND contract_type=? ORDER BY period_no",
            (row['project_id'], row['contract_type'])
        ).fetchall()
        for i, r in enumerate(rows):
            db.execute("UPDATE invoice_periods SET period_no=? WHERE id=?", (i+1, r['id']))
    db.commit()
    return jsonify({'ok': True})

# ── 請款單列印 ─────────────────────────────────────────────────────────
@app.route('/invoice/<int:iid>/print')
def invoice_print(iid):
    db = get_db()
    period  = db.execute("SELECT * FROM invoice_periods WHERE id=?", (iid,)).fetchone()
    if not period: return "not found", 404
    period  = dict(period)
    project = dict(db.execute("SELECT * FROM projects WHERE id=?", (period['project_id'],)).fetchone())
    company = dict(db.execute("SELECT * FROM company_info WHERE id=1").fetchone())
    ct = period['contract_type']
    all_periods = [dict(r) for r in db.execute(
        "SELECT * FROM invoice_periods WHERE project_id=? AND contract_type=? ORDER BY period_no",
        (project['id'], ct)
    )]
    total_periods = len(all_periods)
    received_sum  = sum(p['amount'] for p in all_periods if p['status'] == 'received')
    contract_amount = project['design_contract'] if ct == 'design' else project['engineering_contract']

    import base64
    logo_b64 = ''
    logo_path = os.path.join(BASE_DIR, 'data', 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    return render_template('invoice_print.html',
        period=period, project=project, company=company,
        all_periods=all_periods, total_periods=total_periods,
        received_sum=received_sum, contract_amount=contract_amount,
        logo_b64=logo_b64, fmt=fmt)

# ── Finance pages ─────────────────────────────────────────────────────
@app.route('/finance')
def finance():
    db = get_db()
    projects = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY name")]
    return render_template('finance.html', projects=projects, fmt=fmt)

@app.route('/finance/vendors')
def finance_vendors():
    db = get_db()
    vendors  = [dict(r) for r in db.execute("SELECT * FROM vendors ORDER BY name")]
    projects = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY name")]
    pending  = [dict(r) for r in db.execute("""
        SELECT vi.*, v.bank_account, v.bank_holder, v.bank_name,
               p.name as project_name
        FROM vendor_invoices vi
        LEFT JOIN vendors v ON vi.vendor_id=v.id
        LEFT JOIN projects p ON vi.project_id=p.id
        WHERE vi.status='pending'
        ORDER BY vi.due_date
    """)]
    paid = [dict(r) for r in db.execute("""
        SELECT vi.*, v.name as vendor_main_name,
               p.name as project_name
        FROM vendor_invoices vi
        LEFT JOIN vendors v ON vi.vendor_id=v.id
        LEFT JOIN projects p ON vi.project_id=p.id
        WHERE vi.status='paid'
        ORDER BY vi.paid_date DESC LIMIT 50
    """)]
    from datetime import date
    return render_template('finance_vendors.html',
        vendors=vendors, projects=projects, pending=pending, paid=paid,
        fmt=fmt, now=date.today().isoformat())

@app.route('/api/vendor', methods=['POST'])
def api_vendor_add():
    db = get_db()
    d = request.json
    db.execute("""
        INSERT INTO vendors (name,contact,tel,category,bank_name,bank_account,bank_holder,note)
        VALUES (?,?,?,?,?,?,?,?)
    """, (d['name'], d.get('contact',''), d.get('tel',''),
          d.get('category',''), d.get('bank_name',''),
          d.get('bank_account',''), d.get('bank_holder',''), d.get('note','')))
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({'ok': True, 'id': new_id})

@app.route('/api/vendor/<int:vid>', methods=['PATCH'])
def api_vendor_update(vid):
    db = get_db()
    d = request.json
    fields, vals = [], []
    for k in ('name','contact','tel','category','bank_name','bank_account','bank_holder','note'):
        if k in d:
            fields.append(f"{k}=?")
            vals.append(d[k])
    if not fields: return jsonify({'ok': False})
    vals.append(vid)
    db.execute(f"UPDATE vendors SET {','.join(fields)} WHERE id=?", vals)
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vendor/<int:vid>', methods=['DELETE'])
def api_vendor_delete(vid):
    db = get_db()
    db.execute("DELETE FROM vendors WHERE id=?", (vid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vendor/<int:vid>', methods=['GET'])
def api_vendor_get(vid):
    db = get_db()
    v = db.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone()
    return jsonify(dict(v) if v else {})

@app.route('/api/vendor-invoice', methods=['POST'])
def api_vendor_invoice_add():
    db = get_db()
    d = request.json
    db.execute("""
        INSERT INTO vendor_invoices
            (vendor_id,project_id,vendor_name,period_name,due_date,amount,
             tax_setting,invoice_status,invoice_no,note,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,'pending')
    """, (d.get('vendor_id'), d.get('project_id'),
          d.get('vendor_name',''), d.get('period_name',''),
          d.get('due_date',''), float(d.get('amount',0)),
          d.get('tax_setting','未稅'), d.get('invoice_status','無發票'),
          d.get('invoice_no',''), d.get('note','')))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vendor-invoice/<int:iid>/pay', methods=['POST'])
def api_vendor_invoice_pay(iid):
    db = get_db()
    d = request.json
    db.execute("""
        UPDATE vendor_invoices SET
            status='paid', paid_date=?, payment_method=?, paid_account=?
        WHERE id=?
    """, (d.get('paid_date',''), d.get('payment_method',''),
          d.get('paid_account',''), iid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vendor-invoice/<int:iid>', methods=['DELETE'])
def api_vendor_invoice_delete(iid):
    db = get_db()
    db.execute("DELETE FROM vendor_invoices WHERE id=?", (iid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/finance/expenses')
def finance_expenses():
    db = get_db()
    expenses = [dict(r) for r in db.execute("SELECT * FROM company_expenses ORDER BY date DESC")]
    return render_template('finance_expenses.html', expenses=expenses, fmt=fmt)

@app.route('/finance/report')
def finance_report():
    db = get_db()
    design_income  = db.execute("SELECT COALESCE(SUM(amount),0) as v FROM invoice_periods WHERE status='received' AND contract_type='design'").fetchone()['v']
    eng_income     = db.execute("SELECT COALESCE(SUM(amount),0) as v FROM invoice_periods WHERE status='received' AND contract_type='construction'").fetchone()['v']
    vendor_expense = db.execute("SELECT COALESCE(SUM(amount),0) as v FROM vendor_payments WHERE status='paid'").fetchone()['v']
    company_expense= db.execute("SELECT COALESCE(SUM(amount),0) as v FROM company_expenses").fetchone()['v']
    total_income   = design_income + eng_income
    total_expense  = vendor_expense + company_expense
    profit         = total_income - total_expense

    projects = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY name")]
    project_stats_list = []
    for p in projects:
        st = project_stats(db, p['id'])
        vp = db.execute("SELECT COALESCE(SUM(amount),0) as v FROM vendor_payments WHERE project_id=?", (p['id'],)).fetchone()['v']
        project_stats_list.append({**p, **st, 'vendor_expense': vp,
                                    'profit': st['total_received'] - vp})

    return render_template('finance_report.html',
        design_income=design_income, eng_income=eng_income,
        vendor_expense=vendor_expense, company_expense=company_expense,
        total_income=total_income, total_expense=total_expense, profit=profit,
        project_stats=project_stats_list, fmt=fmt)

# ── API: vendor payments ──────────────────────────────────────────────
@app.route('/api/vendor-payment', methods=['POST'])
def api_vendor_payment_add():
    db = get_db()
    d = request.json
    db.execute("""
        INSERT INTO vendor_payments
            (project_id,vendor_name,category,period_name,date,amount,fee,
             tax_setting,payment_method,invoice_status,invoice_no,status,note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (d.get('project_id'), d.get('vendor_name',''), d.get('category',''),
          d.get('period_name',''), d.get('date',''), float(d.get('amount',0)),
          float(d.get('fee',0)), d.get('tax_setting','未稅'),
          d.get('payment_method',''), d.get('invoice_status','無發票'),
          d.get('invoice_no',''), 'paid', d.get('note','')))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vendor-payment/<int:vid>', methods=['DELETE'])
def api_vendor_payment_delete(vid):
    db = get_db()
    db.execute("DELETE FROM vendor_payments WHERE id=?", (vid,))
    db.commit()
    return jsonify({'ok': True})

# ── API: company expense ──────────────────────────────────────────────
@app.route('/api/expense', methods=['POST'])
def api_expense_add():
    db = get_db()
    d = request.json
    db.execute("""
        INSERT INTO company_expenses
            (date,category,item,vendor,amount,tax_setting,payment_method,
             invoice_status,invoice_no,recurring,note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (d.get('date',''), d.get('category',''), d.get('item',''),
          d.get('vendor',''), float(d.get('amount',0)), d.get('tax_setting','含稅'),
          d.get('payment_method',''), d.get('invoice_status','無發票'),
          d.get('invoice_no',''), d.get('recurring','否'), d.get('note','')))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/expense/<int:eid>', methods=['DELETE'])
def api_expense_delete(eid):
    db = get_db()
    db.execute("DELETE FROM company_expenses WHERE id=?", (eid,))
    db.commit()
    return jsonify({'ok': True})

# ── Settings ──────────────────────────────────────────────────────────
@app.route('/settings', methods=['GET','POST'])
def settings():
    db = get_db()
    if request.method == 'POST':
        d = request.form
        db.execute("""
            UPDATE company_info SET name=?,name_en=?,tax_id=?,address=?,
                tel=?,email=?,bank_name=?,bank_account=?,bank_account_name=?
            WHERE id=1
        """, (d.get('name','漣一設計有限公司'), d.get('name_en','LA DURÉE'),
              d.get('tax_id',''), d.get('address',''), d.get('tel',''),
              d.get('email',''), d.get('bank_name',''),
              d.get('bank_account',''), d.get('bank_account_name','')))
        db.commit()
        if 'logo' in request.files:
            f = request.files['logo']
            if f and f.filename:
                f.save(os.path.join(BASE_DIR, 'data', 'logo.png'))
        return redirect(url_for('settings'))

    company = dict(db.execute("SELECT * FROM company_info WHERE id=1").fetchone())
    import base64
    logo_b64 = ''
    logo_path = os.path.join(BASE_DIR, 'data', 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path,'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()
    return render_template('settings.html', company=company, logo_b64=logo_b64)

# ── Backup / Restore ─────────────────────────────────────────────────
@app.route('/api/backup', methods=['GET'])
def api_backup():
    from flask import Response
    from datetime import datetime
    db = get_db()

    def rows(table):
        return [dict(r) for r in db.execute(f"SELECT * FROM {table}")]

    data = {
        'backup_version': '2.0',
        'backup_date': datetime.now().isoformat(),
        'projects':          rows('projects'),
        'invoice_periods':   rows('invoice_periods'),
        'vendors':           rows('vendors'),
        'vendor_contracts':  rows('vendor_contracts'),
        'vendor_invoices':   rows('vendor_invoices'),
        'vendor_payments':   rows('vendor_payments'),
        'company_expenses':  rows('company_expenses'),
        'extra_works':       rows('extra_works'),
        'pending_payments':  rows('pending_payments'),
        'company_info':      rows('company_info'),
    }
    filename = f"laduree-ops-backup-{datetime.now().strftime('%Y-%m-%d-%H-%M')}.json"
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/api/restore', methods=['POST'])
def api_restore():
    db = get_db()
    data = request.json
    version = data.get('backup_version', '1.0')
    counts = {}

    # 如果是新版備份（有 vendors 表）
    if version == '2.0':
        # vendors
        for v in data.get('vendors', []):
            if not db.execute("SELECT id FROM vendors WHERE id=?", (v['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO vendors
                        (id,name,contact,tel,category,bank_name,bank_account,bank_holder,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (v['id'], v.get('name',''), v.get('contact',''), v.get('tel',''),
                      v.get('category',''), v.get('bank_name',''), v.get('bank_account',''),
                      v.get('bank_holder',''), v.get('note',''), v.get('created_at','')))
                counts['vendors'] = counts.get('vendors',0) + 1

        # vendor_invoices
        for vi in data.get('vendor_invoices', []):
            if not db.execute("SELECT id FROM vendor_invoices WHERE id=?", (vi['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO vendor_invoices
                        (id,vendor_id,project_id,vendor_name,period_name,due_date,amount,
                         tax_setting,invoice_status,invoice_no,note,status,paid_date,payment_method,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (vi['id'], vi.get('vendor_id'), vi.get('project_id'),
                      vi.get('vendor_name',''), vi.get('period_name',''), vi.get('due_date',''),
                      vi.get('amount',0), vi.get('tax_setting','未稅'),
                      vi.get('invoice_status','無發票'), vi.get('invoice_no',''),
                      vi.get('note',''), vi.get('status','pending'),
                      vi.get('paid_date',''), vi.get('payment_method',''), vi.get('created_at','')))
                counts['vendor_invoices'] = counts.get('vendor_invoices',0) + 1

        # projects
        for p in data.get('projects', []):
            if not db.execute("SELECT id FROM projects WHERE id=?", (p['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO projects
                        (id,legacy_id,code,name,client_name,client_tel,client_email,
                         address,start_date,status,design_contract,design_tax,
                         engineering_contract,engineering_tax,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (p['id'], p.get('legacy_id'), p.get('code',''), p.get('name',''),
                      p.get('client_name',''), p.get('client_tel',''), p.get('client_email',''),
                      p.get('address',''), p.get('start_date',''), p.get('status','active'),
                      p.get('design_contract',0), p.get('design_tax','未稅'),
                      p.get('engineering_contract',0), p.get('engineering_tax','未稅'),
                      p.get('note',''), p.get('created_at','')))
                counts['projects'] = counts.get('projects',0) + 1

        # invoice_periods
        for ip in data.get('invoice_periods', []):
            if not db.execute("SELECT id FROM invoice_periods WHERE id=?", (ip['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO invoice_periods
                        (id,project_id,period_no,contract_type,label,ratio,amount,
                         due_date,payment_method,account_last5,has_invoice,invoice_no,
                         invoice_date,received_date,status,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (ip['id'], ip.get('project_id'), ip.get('period_no',1),
                      ip.get('contract_type','design'), ip.get('label',''),
                      ip.get('ratio',0), ip.get('amount',0), ip.get('due_date',''),
                      ip.get('payment_method',''), ip.get('account_last5',''),
                      ip.get('has_invoice',0), ip.get('invoice_no',''),
                      ip.get('invoice_date',''), ip.get('received_date',''),
                      ip.get('status','pending'), ip.get('note',''), ip.get('created_at','')))
                counts['invoice_periods'] = counts.get('invoice_periods',0) + 1

        # vendor_payments
        for vp in data.get('vendor_payments', []):
            if not db.execute("SELECT id FROM vendor_payments WHERE id=?", (vp['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO vendor_payments
                        (id,legacy_id,vendor_id,project_id,vendor_name,category,
                         period_name,date,amount,fee,tax_setting,payment_method,
                         account_no,invoice_status,invoice_no,status,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (vp['id'], vp.get('legacy_id'), vp.get('vendor_id'), vp.get('project_id'),
                      vp.get('vendor_name',''), vp.get('category',''), vp.get('period_name',''),
                      vp.get('date',''), vp.get('amount',0), vp.get('fee',0),
                      vp.get('tax_setting','未稅'), vp.get('payment_method',''),
                      vp.get('account_no',''), vp.get('invoice_status','無發票'),
                      vp.get('invoice_no',''), vp.get('status','已付'),
                      vp.get('note',''), vp.get('created_at','')))
                counts['vendor_payments'] = counts.get('vendor_payments',0) + 1

        # company_expenses
        for ce in data.get('company_expenses', []):
            if not db.execute("SELECT id FROM company_expenses WHERE id=?", (ce['id'],)).fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO company_expenses
                        (id,legacy_id,date,category,item,vendor,amount,tax_setting,
                         payment_method,invoice_status,invoice_no,recurring,note,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (ce['id'], ce.get('legacy_id'), ce.get('date',''), ce.get('category',''),
                      ce.get('item',''), ce.get('vendor',''), ce.get('amount',0),
                      ce.get('tax_setting','含稅'), ce.get('payment_method',''),
                      ce.get('invoice_status','無發票'), ce.get('invoice_no',''),
                      ce.get('recurring','否'), ce.get('note',''), ce.get('created_at','')))
                counts['company_expenses'] = counts.get('company_expenses',0) + 1

        db.commit()
        return jsonify({'ok': True, 'restored': counts})

    # 舊版財務備份（version 1.0 / 無版本號）直接轉給 import
    return api_import()

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5006, debug=True)
