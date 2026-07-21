# ── Finance v3 — Database-First 重構 Phase 0 ─────────────────────────────
# 新的核心資料表（categories / vendors / projects / contracts / income /
# expenses）與舊表「並行」建立，不影響現有已部署的頁面。
# 提供舊資料 migration（支援 localStorage 版與 Flask v2.0 備份）與新舊對帳。
#
# 設計原則：以「交易」為中心、字典正規化、金額只存一處；累積/剩餘/毛利等
# 全部由 GROUP BY 即時算出，不重複儲存。
import os
from flask import Blueprint, request, jsonify

bp = Blueprint('finance_v3', __name__)

# 這些 helper 在 app.server 內；用時才 import 以避免 import 期循環相依。
def _srv():
    from app import server as s
    return s

# ── 預設字典 ──────────────────────────────────────────────────────────
DEFAULT_TRADES = ['木工','水電','泥作','油漆','防水','玻璃','鋁窗','系統櫃',
                  '鐵件','PVC','地板','磁磚','石材','衛浴','廚具','空調',
                  '清潔','保護工程','拆除工程','材料採購','其他']
DEFAULT_INCOME_TYPES = ['設計費','工程款','追加款','減項','退款','其他']
DEFAULT_COMPANY_EXP  = ['房租','薪資','軟體訂閱','行銷','交通','稅務','雜支','其他']

# ── Schema（SQLite / Postgres）────────────────────────────────────────
DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,                      -- trade | income_type | company_expense
  name TEXT NOT NULL,
  sort_order INTEGER DEFAULT 0,
  color TEXT DEFAULT '',
  active INTEGER DEFAULT 1,
  UNIQUE(kind, name)
);
CREATE TABLE IF NOT EXISTS vendors_v3 (
  id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
  name TEXT NOT NULL, category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  contact TEXT DEFAULT '', tel TEXT DEFAULT '',
  bank_name TEXT DEFAULT '', bank_account TEXT DEFAULT '', bank_holder TEXT DEFAULT '',
  tax_id TEXT DEFAULT '', note TEXT DEFAULT '', active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS projects_v3 (
  id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE, code TEXT,
  name TEXT NOT NULL, client_name TEXT DEFAULT '', client_tel TEXT DEFAULT '',
  client_email TEXT DEFAULT '', address TEXT DEFAULT '',
  status TEXT DEFAULT 'active',             -- lead|active|completed|paused|archived
  start_date TEXT DEFAULT '', end_date TEXT DEFAULT '',
  design_fee REAL DEFAULT 0, construction_contract REAL DEFAULT 0,
  note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
  project_id INTEGER REFERENCES projects_v3(id) ON DELETE CASCADE,
  vendor_id INTEGER REFERENCES vendors_v3(id) ON DELETE SET NULL,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  amount REAL DEFAULT 0, signed_date TEXT DEFAULT '', note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS income (
  id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
  project_id INTEGER REFERENCES projects_v3(id) ON DELETE CASCADE,
  date TEXT DEFAULT '', due_date TEXT DEFAULT '', period_no INTEGER DEFAULT 1,
  type_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  amount REAL DEFAULT 0, tax_setting TEXT DEFAULT '未稅',
  bank_account TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',            -- pending|received
  received_date TEXT DEFAULT '', invoice_no TEXT DEFAULT '',
  note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, legacy_id TEXT UNIQUE,
  project_id INTEGER REFERENCES projects_v3(id) ON DELETE SET NULL,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  vendor_id INTEGER REFERENCES vendors_v3(id) ON DELETE SET NULL,
  contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
  item TEXT DEFAULT '', amount REAL DEFAULT 0,
  date TEXT DEFAULT '', due_date TEXT DEFAULT '',
  status TEXT DEFAULT 'paid',               -- pending|paid
  tax_rate REAL DEFAULT 0, invoice_no TEXT DEFAULT '',
  payment_method TEXT DEFAULT '', note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

# Postgres 版：型別差異（SERIAL / REAL→DOUBLE PRECISION / TEXT default now）
DDL_PG = (DDL_SQLITE
          .replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
          .replace('REAL', 'DOUBLE PRECISION')
          .replace("TEXT DEFAULT (datetime('now','localtime'))", 'TIMESTAMP DEFAULT NOW()'))


def init_v3():
    """建立 v3 新表並種入預設字典。冪等，可多 worker 併發呼叫。"""
    url = os.environ.get('DATABASE_URL', '')
    if 'postgres' in url:
        import psycopg2
        conn = psycopg2.connect(url); cur = conn.cursor()
        for stmt in DDL_PG.split(';'):
            if stmt.strip(): cur.execute(stmt)
        _seed_categories_pg(cur)
        conn.commit(); conn.close()
    else:
        import sqlite3
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(os.path.join(base, 'data'), exist_ok=True)
        conn = sqlite3.connect(os.path.join(base, 'data', 'ops.db'))
        conn.executescript(DDL_SQLITE)
        _seed_categories_sqlite(conn)
        conn.commit(); conn.close()


def _seed_pairs():
    pairs = []
    for i, n in enumerate(DEFAULT_TRADES):        pairs.append(('trade', n, i))
    for i, n in enumerate(DEFAULT_INCOME_TYPES):  pairs.append(('income_type', n, i))
    for i, n in enumerate(DEFAULT_COMPANY_EXP):   pairs.append(('company_expense', n, i))
    return pairs

def _seed_categories_sqlite(conn):
    for kind, name, so in _seed_pairs():
        conn.execute("INSERT OR IGNORE INTO categories (kind,name,sort_order) VALUES (?,?,?)",
                     (kind, name, so))

def _seed_categories_pg(cur):
    for kind, name, so in _seed_pairs():
        cur.execute("INSERT INTO categories (kind,name,sort_order) VALUES (%s,%s,%s) "
                    "ON CONFLICT (kind,name) DO NOTHING", (kind, name, so))


# ── 字典 get-or-create ────────────────────────────────────────────────
def _cat_id(kind, name):
    """回傳 categories.id，不存在則新增。空名稱回 None。"""
    s = _srv(); ph = s._ph()
    name = (name or '').strip()
    if not name:
        return None
    row = s.fetchone(f"SELECT id FROM categories WHERE kind={ph} AND name={ph}", (kind, name))
    if row:
        return row['id']
    s.execute(f"INSERT INTO categories (kind,name,sort_order) VALUES ({ph},{ph},999)", (kind, name))
    return s.last_insert_id()


# ── Migration：舊 JSON → v3 ───────────────────────────────────────────
STATUS_MAP = {'進行中':'active','施工中':'active','設計中':'lead','已完工':'completed',
              '完工':'completed','暫停':'paused','已封存':'archived'}

def _detect_format(data):
    if 'periods' in data or 'vendor-contracts' in data or 'company-expenses' in data:
        return 'local'
    if 'invoice_periods' in data or str(data.get('backup_version','')).startswith('2'):
        return 'flask'
    return 'local'


def migrate_legacy(data):
    """把舊備份 JSON 匯入 v3 新表。冪等（以 legacy_id 去重）。回傳匯入統計。"""
    fmt = _detect_format(data)
    if fmt == 'flask':
        return _migrate_flask(data)
    return _migrate_local(data)


def _trade_of(vendor_name, category):
    """工種判定：category 若是通用值（工程/其他/空）則從『工種/人名』前綴回推。"""
    category = (category or '').strip()
    if category and category not in ('工程', '其他'):
        return category
    vn = (vendor_name or '').strip()
    if '/' in vn:
        pre = vn.split('/', 1)[0].strip()
        if pre:
            return pre
    return category or '其他'

def _vendor_by_name(name, trade):
    """以廠商名 get-or-create（原始資料無 vendors 主檔時用）。冪等。"""
    s = _srv(); ph = s._ph()
    name = (name or '').strip()
    if not name:
        return None
    row = s.fetchone(f"SELECT id FROM vendors_v3 WHERE name={ph}", (name,))
    if row:
        return row['id']
    s.execute(f"INSERT INTO vendors_v3 (legacy_id,name,category_id) VALUES ({ph},{ph},{ph})",
              ('vn-'+name, name, _cat_id('trade', trade)))
    return s.last_insert_id()


def _migrate_local(data):
    s = _srv(); ph = s._ph(); c = {}
    # vendors（若備份有主檔則用之；本專案備份 vendors 為空，改由付款/合約的
    # vendorName 自動建立，見 _vendor_by_name）
    vmap = {}   # legacy vendor id -> new id
    for v in data.get('vendors', []):
        lid = str(v.get('id'))
        row = s.fetchone(f"SELECT id FROM vendors_v3 WHERE legacy_id={ph}", (lid,))
        if row: vmap[lid] = row['id']; continue
        cid = _cat_id('trade', v.get('category',''))
        s.execute(f"""INSERT INTO vendors_v3 (legacy_id,name,category_id,contact,tel,
            bank_name,bank_account,bank_holder,tax_id,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, v.get('name',''), cid, v.get('contact',''), v.get('tel',''),
             v.get('bankName',v.get('bank_name','')), v.get('bankAccount',v.get('bank_account','')),
             v.get('bankHolder',v.get('bank_holder','')), v.get('taxId',v.get('tax_id','')),
             v.get('note','')))
        vmap[lid] = s.last_insert_id(); c['vendors'] = c.get('vendors',0)+1
    # projects
    pmap = {}
    for p in data.get('projects', []):
        lid = str(p.get('id'))
        row = s.fetchone(f"SELECT id FROM projects_v3 WHERE legacy_id={ph}", (lid,))
        if row: pmap[lid] = row['id']; continue
        s.execute(f"""INSERT INTO projects_v3 (legacy_id,name,client_name,address,
            status,start_date,end_date,design_fee,construction_contract,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, p.get('name',''), p.get('client',p.get('clientName','')),
             p.get('address',''), STATUS_MAP.get(p.get('status',''),'active'),
             p.get('startDate',''), p.get('endDate',''),
             float(p.get('designContract',0) or 0), float(p.get('engineeringContract',0) or 0),
             p.get('note','')))
        pmap[lid] = s.last_insert_id(); c['projects'] = c.get('projects',0)+1
    # periods -> income
    for pr in data.get('periods', []):
        lid = 'per-'+str(pr.get('id'))
        if s.fetchone(f"SELECT id FROM income WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(pr.get('projectId')))
        if not pid: continue
        it = '設計費' if pr.get('contractType')=='設計費' else '工程款'
        tid = _cat_id('income_type', it)
        recv = pr.get('status') in ('已收','received')
        s.execute(f"""INSERT INTO income (legacy_id,project_id,date,due_date,period_no,
            type_id,amount,tax_setting,status,received_date,invoice_no,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, pr.get('dueDate',''), pr.get('dueDate',''), pr.get('periodNo',1),
             tid, float(pr.get('amount',0) or 0), pr.get('taxSetting','未稅'),
             'received' if recv else 'pending', pr.get('receivedDate',''),
             pr.get('invoiceNo',''), pr.get('note','')))
        c['income'] = c.get('income',0)+1
    # extra-works -> income (追加款/減項)
    for e in data.get('extra-works', data.get('extras', [])):
        lid = 'ex-'+str(e.get('id'))
        if s.fetchone(f"SELECT id FROM income WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(e.get('projectId')))
        it = '追加款' if e.get('type')=='追加' else '減項'
        s.execute(f"""INSERT INTO income (legacy_id,project_id,date,type_id,amount,
            status,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, e.get('date',''), _cat_id('income_type', it),
             float(e.get('amount',0) or 0), 'received', e.get('description',e.get('note',''))))
        c['income_extra'] = c.get('income_extra',0)+1
    # vendor-contracts -> contracts（vendorId 缺漏時以 vendorName 建立廠商；
    # category 通用「工程」時從 vendorName 前綴回推工種）
    cmap = {}
    for vc in data.get('vendor-contracts', data.get('vcs', [])):
        lid = 'vc-'+str(vc.get('id'))
        row = s.fetchone(f"SELECT id FROM contracts WHERE legacy_id={ph}", (lid,))
        if row: cmap[str(vc.get('id'))] = row['id']; continue
        pid = pmap.get(str(vc.get('projectId')))
        trade = _trade_of(vc.get('vendorName',''), vc.get('category',''))
        vid = vmap.get(str(vc.get('vendorId'))) or _vendor_by_name(vc.get('vendorName',''), trade)
        cid = _cat_id('trade', trade)
        s.execute(f"""INSERT INTO contracts (legacy_id,project_id,vendor_id,category_id,amount,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, vid, cid, float(vc.get('contractTotal',0) or 0), vc.get('note','')))
        cmap[str(vc.get('id'))] = s.last_insert_id(); c['contracts'] = c.get('contracts',0)+1
    # vendor-payments -> expenses
    vc_by_id = {str(x.get('id')): x for x in data.get('vendor-contracts', data.get('vcs', []))}
    for vp in data.get('vendor-payments', data.get('vps', [])):
        lid = 'vp-'+str(vp.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(vp.get('projectId')))
        cnid = cmap.get(str(vp.get('vendorContractId')))
        vc = vc_by_id.get(str(vp.get('vendorContractId')))
        vname = vp.get('vendorName') or (vc.get('vendorName','') if vc else '')
        trade = _trade_of(vname, vp.get('category',''))
        cid = _cat_id('trade', trade)
        vid = _vendor_by_name(vname, trade)
        # vendor-payment = 已發生的付款；除非明確標未付，否則視為已付
        vp_status = 'pending' if str(vp.get('status')) in ('待付','pending','未付') else 'paid'
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,vendor_id,
            contract_id,item,amount,date,status,invoice_no,payment_method,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, cid, vid, cnid, vp.get('periodName',''),
             float(vp.get('amount',0) or 0)+float(vp.get('fee',0) or 0),
             vp.get('date',''), vp_status,
             vp.get('invoiceNo',''), vp.get('paymentMethod',''), vp.get('note','')))
        c['expenses'] = c.get('expenses',0)+1
    # pending-payments -> expenses(pending)（尚未付款的廠商帳單）
    for pp in data.get('pending-payments', []):
        lid = 'pp-'+str(pp.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(pp.get('projectId')))
        vname = pp.get('vendorName','')
        trade = _trade_of(vname, pp.get('category',''))
        vid = _vendor_by_name(vname, trade)
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,vendor_id,
            item,amount,date,due_date,status,payment_method,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},'pending',{ph},{ph})""",
            (lid, pid, _cat_id('trade', trade), vid, pp.get('category',''),
             float(pp.get('amount',0) or 0), '', pp.get('dueDate',''),
             pp.get('paymentMethod',''), pp.get('note','')))
        c['expenses_pending'] = c.get('expenses_pending',0)+1
    # purchases -> expenses（工種=材料採購）
    for pu in data.get('purchases', []):
        if pu.get('returned') == '是': continue
        lid = 'pu-'+str(pu.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(pu.get('projectId')))
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,item,amount,
            date,status,note) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, _cat_id('trade','材料採購'), pu.get('item',pu.get('name','')),
             float(pu.get('amount',0) or 0), pu.get('date',''), 'paid', pu.get('note','')))
        c['expenses_purchase'] = c.get('expenses_purchase',0)+1
    # company-expenses -> expenses（project_id NULL）
    for ce in data.get('company-expenses', data.get('coExpenses', [])):
        lid = 'ce-'+str(ce.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,vendor_id,
            item,amount,date,status,invoice_no,payment_method,note)
            VALUES ({ph},NULL,{ph},NULL,{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, _cat_id('company_expense', ce.get('category','其他')),
             ce.get('item',''), float(ce.get('amount',0) or 0), ce.get('date',''),
             'paid', ce.get('invoiceNo',''), ce.get('paymentMethod',''), ce.get('note','')))
        c['expenses_company'] = c.get('expenses_company',0)+1
    s.commit()
    return c


def _migrate_flask(data):
    """Flask v2.0 備份 → v3。欄位已是 snake_case。"""
    s = _srv(); ph = s._ph(); c = {}
    vmap, pmap, cmap = {}, {}, {}
    for v in data.get('vendors', []):
        lid = 'fv-'+str(v.get('id'))
        row = s.fetchone(f"SELECT id FROM vendors_v3 WHERE legacy_id={ph}", (lid,))
        if row: vmap[str(v.get('id'))] = row['id']; continue
        s.execute(f"""INSERT INTO vendors_v3 (legacy_id,name,category_id,contact,tel,
            bank_name,bank_account,bank_holder,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, v.get('name',''), _cat_id('trade', v.get('category','')),
             v.get('contact',''), v.get('tel',''), v.get('bank_name',''),
             v.get('bank_account',''), v.get('bank_holder',''), v.get('note','')))
        vmap[str(v.get('id'))] = s.last_insert_id(); c['vendors'] = c.get('vendors',0)+1
    for p in data.get('projects', []):
        lid = 'fp-'+str(p.get('id'))
        row = s.fetchone(f"SELECT id FROM projects_v3 WHERE legacy_id={ph}", (lid,))
        if row: pmap[str(p.get('id'))] = row['id']; continue
        s.execute(f"""INSERT INTO projects_v3 (legacy_id,code,name,client_name,client_tel,
            client_email,address,status,start_date,design_fee,construction_contract,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, p.get('code',''), p.get('name',''), p.get('client_name',''),
             p.get('client_tel',''), p.get('client_email',''), p.get('address',''),
             p.get('status','active'), p.get('start_date',''),
             float(p.get('design_contract',0) or 0), float(p.get('engineering_contract',0) or 0),
             p.get('note','')))
        pmap[str(p.get('id'))] = s.last_insert_id(); c['projects'] = c.get('projects',0)+1
    for ip in data.get('invoice_periods', []):
        lid = 'fip-'+str(ip.get('id'))
        if s.fetchone(f"SELECT id FROM income WHERE legacy_id={ph}", (lid,)): continue
        pid = pmap.get(str(ip.get('project_id')))
        if not pid: continue
        it = '設計費' if ip.get('contract_type')=='design' else '工程款'
        recv = ip.get('status')=='received'
        s.execute(f"""INSERT INTO income (legacy_id,project_id,date,due_date,period_no,
            type_id,amount,tax_setting,status,received_date,invoice_no,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pid, ip.get('due_date',''), ip.get('due_date',''), ip.get('period_no',1),
             _cat_id('income_type', it), float(ip.get('amount',0) or 0),
             ip.get('tax_setting','未稅'), 'received' if recv else 'pending',
             ip.get('received_date',''), ip.get('invoice_no',''), ip.get('note','')))
        c['income'] = c.get('income',0)+1
    for vc in data.get('vendor_contracts', []):
        lid = 'fvc-'+str(vc.get('id'))
        row = s.fetchone(f"SELECT id FROM contracts WHERE legacy_id={ph}", (lid,))
        if row: cmap[str(vc.get('id'))] = row['id']; continue
        s.execute(f"""INSERT INTO contracts (legacy_id,project_id,vendor_id,category_id,amount,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pmap.get(str(vc.get('project_id'))), vmap.get(str(vc.get('vendor_id'))),
             _cat_id('trade', vc.get('category','')), float(vc.get('amount',0) or 0), vc.get('note','')))
        cmap[str(vc.get('id'))] = s.last_insert_id(); c['contracts'] = c.get('contracts',0)+1
    for vp in data.get('vendor_payments', []):
        lid = 'fvp-'+str(vp.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,vendor_id,
            item,amount,date,status,invoice_no,payment_method,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pmap.get(str(vp.get('project_id'))), _cat_id('trade', vp.get('category','')),
             vmap.get(str(vp.get('vendor_id'))), vp.get('period_name',''),
             float(vp.get('amount',0) or 0)+float(vp.get('fee',0) or 0), vp.get('date',''),
             'paid' if vp.get('status') in ('已付','paid') else 'pending',
             vp.get('invoice_no',''), vp.get('payment_method',''), vp.get('note','')))
        c['expenses'] = c.get('expenses',0)+1
    for vi in data.get('vendor_invoices', []):
        lid = 'fvi-'+str(vi.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,vendor_id,item,amount,
            date,due_date,status,invoice_no,payment_method,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pmap.get(str(vi.get('project_id'))), vmap.get(str(vi.get('vendor_id'))),
             vi.get('period_name',''), float(vi.get('amount',0) or 0),
             vi.get('paid_date',''), vi.get('due_date',''),
             'paid' if vi.get('status')=='paid' else 'pending',
             vi.get('invoice_no',''), vi.get('payment_method',''), vi.get('note','')))
        c['expenses_inv'] = c.get('expenses_inv',0)+1
    for ce in data.get('company_expenses', []):
        lid = 'fce-'+str(ce.get('id'))
        if s.fetchone(f"SELECT id FROM expenses WHERE legacy_id={ph}", (lid,)): continue
        s.execute(f"""INSERT INTO expenses (legacy_id,project_id,category_id,item,amount,
            date,status,invoice_no,payment_method,note)
            VALUES ({ph},NULL,{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, _cat_id('company_expense', ce.get('category','其他')), ce.get('item',''),
             float(ce.get('amount',0) or 0), ce.get('date',''), 'paid',
             ce.get('invoice_no',''), ce.get('payment_method',''), ce.get('note','')))
        c['expenses_company'] = c.get('expenses_company',0)+1
    for e in data.get('extra_works', []):
        lid = 'fex-'+str(e.get('id'))
        if s.fetchone(f"SELECT id FROM income WHERE legacy_id={ph}", (lid,)): continue
        it = '追加款' if e.get('type')=='追加' else '減項'
        s.execute(f"""INSERT INTO income (legacy_id,project_id,date,type_id,amount,status,note)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (lid, pmap.get(str(e.get('project_id'))), e.get('date',''),
             _cat_id('income_type', it), float(e.get('amount',0) or 0), 'received',
             e.get('description', e.get('note',''))))
        c['income_extra'] = c.get('income_extra',0)+1
    s.commit()
    return c


# ── 對帳（新舊總額比對）───────────────────────────────────────────────
def reconcile(data):
    s = _srv()
    def _sum(rows, key='amount', extra=None):
        t = 0.0
        for r in rows:
            t += float(r.get(key,0) or 0) + (float(r.get(extra,0) or 0) if extra else 0)
        return t
    def _extra_net(rows):
        # 追加款為 +、減項為 −（皆計入收入基準，供對帳）
        t = 0.0
        for e in rows:
            a = float(e.get('amount',0) or 0)
            t += a if e.get('type') != '減項' else -a
        return t
    fmt = _detect_format(data)
    if fmt == 'flask':
        old_income = (_sum([p for p in data.get('invoice_periods',[]) if p.get('status')=='received'])
                      + _extra_net(data.get('extra_works',[])))
        old_exp = (_sum([v for v in data.get('vendor_payments',[]) if v.get('status') in ('已付','paid')], extra='fee')
                   + _sum(data.get('company_expenses',[]))
                   + _sum([v for v in data.get('vendor_invoices',[]) if v.get('status')=='paid']))
    else:
        old_income = (_sum([p for p in data.get('periods',[]) if p.get('status')=='已收'])
                      + _extra_net(data.get('extra-works', data.get('extras',[]))))
        # 已付出 = 所有 vendor-payments（原系統視為已發生）+ 採購 + 公司支出；
        # 明確標未付者不計（與 migration 一致）
        old_exp = (_sum([v for v in data.get('vendor-payments', data.get('vps',[]))
                         if str(v.get('status')) not in ('待付','pending','未付')], extra='fee')
                   + _sum([p for p in data.get('purchases',[]) if p.get('returned')!='是'])
                   + _sum(data.get('company-expenses', data.get('coExpenses',[]))))
    new_income = (s.fetchone("SELECT COALESCE(SUM(amount),0) v FROM income WHERE status='received'") or {}).get('v',0)
    new_exp    = (s.fetchone("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE status='paid'") or {}).get('v',0)
    return {
        'format': fmt,
        'income': {'old': round(old_income), 'new': round(new_income or 0),
                   'diff': round((new_income or 0) - old_income)},
        'expense': {'old': round(old_exp), 'new': round(new_exp or 0),
                    'diff': round((new_exp or 0) - old_exp)},
    }


# ── Routes（Phase 0）──────────────────────────────────────────────────
@bp.route('/api/v3/stats')
def v3_stats():
    s = _srv()
    out = {}
    for t in ('categories','vendors_v3','projects_v3','contracts','income','expenses'):
        out[t] = (s.fetchone(f"SELECT COUNT(*) c FROM {t}") or {}).get('c', 0)
    return jsonify(out)

@bp.route('/api/v3/migrate-legacy', methods=['POST'])
def v3_migrate():
    data = request.json or {}
    if not data:
        return jsonify({'ok': False, 'error': 'empty body'}), 400
    counts = migrate_legacy(data)
    rec = reconcile(data)
    return jsonify({'ok': True, 'imported': counts, 'reconcile': rec})

@bp.route('/api/v3/reconcile', methods=['POST'])
def v3_reconcile():
    data = request.json or {}
    return jsonify(reconcile(data))
