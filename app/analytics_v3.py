# ── Finance v3 分析層 ─────────────────────────────────────────────────
# 全部由核心表 GROUP BY 即時算出，不儲存衍生值。供 v3 UI 頁面使用。
from datetime import date

def _srv():
    from app import server as s
    return s

def _one(sql, params=()):
    return (_srv().fetchone(sql, params) or {}).get('v', 0) or 0

def _all(sql, params=()):
    return _srv().fetchall(sql, params)

# ── 專案 ──────────────────────────────────────────────────────────────
def project_rows():
    """每專案：合約/追加/減項/工程總價/已收未收/已付未付/預估實際成本/毛利。"""
    return [_summary(p) for p in
            _all("SELECT * FROM projects_v3 ORDER BY created_at DESC, id DESC")]

def _summary(p):
    """單一專案的金額彙整（收支/成本/毛利），供列表與詳情共用。"""
    s = _srv(); ph = s._ph(); pid = p['id']
    add = _one(f"SELECT COALESCE(SUM(i.amount),0) v FROM income i JOIN categories c ON i.type_id=c.id WHERE i.project_id={ph} AND c.name='追加款'", (pid,))
    ded = _one(f"SELECT COALESCE(SUM(i.amount),0) v FROM income i JOIN categories c ON i.type_id=c.id WHERE i.project_id={ph} AND c.name='減項'", (pid,))
    recv = _one(f"SELECT COALESCE(SUM(amount),0) v FROM income WHERE project_id={ph} AND status='received'", (pid,))
    pend = _one(f"SELECT COALESCE(SUM(amount),0) v FROM income WHERE project_id={ph} AND status='pending'", (pid,))
    paid = _one(f"SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE project_id={ph} AND status='paid'", (pid,))
    unpaid = _one(f"SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE project_id={ph} AND status='pending'", (pid,))
    budget = _one(f"SELECT COALESCE(SUM(amount),0) v FROM contracts WHERE project_id={ph}", (pid,))
    base = (p['design_fee'] or 0) + (p['construction_contract'] or 0) + add - ded
    # 舊案未輸入業主合約金額時，以「已收＋未收」作為工程總價的估算值
    price_est = base <= 0
    total_price = base if not price_est else (recv + pend)
    profit = recv - paid
    return {**p, 'add': add, 'deduct': ded, 'total_price': total_price, 'price_est': price_est,
            'received': recv, 'pending': pend, 'paid': paid, 'unpaid': unpaid,
            'budget': budget, 'actual_cost': paid, 'profit': profit,
            'margin': (profit / recv * 100) if recv else 0,
            'recv_pct': (recv / total_price * 100) if total_price else 0,
            'cost_pct': (paid / budget * 100) if budget else 0}

def project_detail(pid):
    s = _srv(); ph = s._ph()
    p = s.fetchone(f"SELECT * FROM projects_v3 WHERE id={ph}", (pid,))
    if not p:
        return None
    summ = _summary(p)
    income = _all(f"""SELECT i.*, c.name type_name FROM income i
        LEFT JOIN categories c ON i.type_id=c.id WHERE i.project_id={ph}
        ORDER BY i.status, i.due_date""", (pid,))
    exp = _all(f"""SELECT e.*, v.name vendor_name, c.name trade_name FROM expenses e
        LEFT JOIN vendors_v3 v ON e.vendor_id=v.id
        LEFT JOIN categories c ON e.category_id=c.id
        WHERE e.project_id={ph} ORDER BY e.date DESC""", (pid,))
    grouped = {}
    for r in exp:
        grouped.setdefault(r.get('trade_name') or '未分類', []).append(r)
    grouped = dict(sorted(grouped.items(), key=lambda kv: -sum(x['amount'] for x in kv[1])))
    contracts = _all(f"""SELECT ct.*, v.name vendor_name, c.name trade_name,
        (SELECT COALESCE(SUM(amount),0) FROM expenses e WHERE e.contract_id=ct.id AND e.status='paid') paid
        FROM contracts ct LEFT JOIN vendors_v3 v ON ct.vendor_id=v.id
        LEFT JOIN categories c ON ct.category_id=c.id
        WHERE ct.project_id={ph} ORDER BY ct.amount DESC""", (pid,))
    for c in contracts:
        c['remain'] = (c['amount'] or 0) - (c['paid'] or 0)
    return {'p': summ, 'income': income, 'grouped': grouped, 'contracts': contracts,
            'exp_total': sum(r['amount'] for r in exp)}

# ── Dashboard ─────────────────────────────────────────────────────────
def dashboard(year=None, month=None):
    s = _srv()
    y = year or date.today().year
    m = month or date.today().month
    ym = f"{y:04d}-{m:02d}"
    ys = f"{y:04d}"
    mi = _one("SELECT COALESCE(SUM(amount),0) v FROM income   WHERE status='received' AND substr(received_date,1,7)=?", (ym,)) \
       or _one("SELECT COALESCE(SUM(amount),0) v FROM income   WHERE status='received' AND substr(due_date,1,7)=?", (ym,))
    me = _one("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE status='paid' AND substr(date,1,7)=?", (ym,))
    yi = _one("SELECT COALESCE(SUM(amount),0) v FROM income   WHERE status='received' AND (substr(received_date,1,4)=? OR substr(due_date,1,4)=?)", (ys, ys))
    ye = _one("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE status='paid' AND substr(date,1,4)=?", (ys,))
    unrecv = _one("SELECT COALESCE(SUM(amount),0) v FROM income   WHERE status='pending'")
    unpaid = _one("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE status='pending'")
    projs = _srv().fetchall("SELECT status, COUNT(*) c FROM projects_v3 GROUP BY status")
    pc = {r['status']: r['c'] for r in projs}
    recv_all = _one("SELECT COALESCE(SUM(amount),0) v FROM income WHERE status='received'")
    paid_all = _one("SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE status='paid'")
    return {
        'year': y, 'month': m,
        'month_income': mi, 'month_expense': me, 'month_profit': mi - me,
        'month_margin': ((mi - me) / mi * 100) if mi else 0,
        'unreceived': unrecv, 'unpaid': unpaid,
        'year_income': yi, 'year_cost': ye, 'year_profit': yi - ye,
        'total_projects': sum(pc.values()),
        'active': pc.get('active', 0), 'lead': pc.get('lead', 0),
        'completed': pc.get('completed', 0),
        'total_income': recv_all, 'total_paid': paid_all,
    }

def monthly_series(year=None):
    """每月收入/支出/毛利（1-12）供圖表。"""
    y = year or date.today().year
    inc = {r['m']: r['v'] for r in _all(
        "SELECT substr(COALESCE(NULLIF(received_date,''),due_date),6,2) m, SUM(amount) v "
        "FROM income WHERE status='received' AND substr(COALESCE(NULLIF(received_date,''),due_date),1,4)=? "
        "GROUP BY m", (f"{y:04d}",))}
    exp = {r['m']: r['v'] for r in _all(
        "SELECT substr(date,6,2) m, SUM(amount) v FROM expenses "
        "WHERE status='paid' AND substr(date,1,4)=? GROUP BY m", (f"{y:04d}",))}
    rows = []
    for i in range(1, 13):
        mm = f"{i:02d}"
        a = inc.get(mm, 0) or 0; b = exp.get(mm, 0) or 0
        rows.append({'m': i, 'income': a, 'expense': b, 'profit': a - b})
    return rows

# ── 工種 / 廠商 分析 ──────────────────────────────────────────────────
def trade_analysis(year=None):
    where = "WHERE e.status='paid' AND c.kind='trade'"
    params = []
    if year:
        where += " AND substr(e.date,1,4)=?"; params.append(f"{year:04d}")
    return _all(f"""SELECT c.name, COALESCE(SUM(e.amount),0) total, COUNT(*) cnt
        FROM expenses e JOIN categories c ON e.category_id=c.id {where}
        GROUP BY c.id ORDER BY total DESC""", params)

def vendor_analysis(year=None):
    yf = ""
    params = []
    if year:
        yf = " AND substr(e.date,1,4)=?"; params.append(f"{year:04d}")
    return _all(f"""SELECT v.id, v.name,
        COALESCE(SUM(CASE WHEN e.status='paid'    THEN e.amount END),0) paid,
        COALESCE(SUM(CASE WHEN e.status='pending' THEN e.amount END),0) unpaid,
        COUNT(DISTINCT e.project_id) projects, COUNT(e.id) cnt
        FROM vendors_v3 v LEFT JOIN expenses e ON e.vendor_id=v.id{(' AND 1=1'+yf) if yf else ''}
        GROUP BY v.id HAVING paid>0 OR unpaid>0 ORDER BY paid DESC""", params)

def cashflow(year=None):
    """每月 預計/實際 收入、預計/實際 支出。"""
    y = year or date.today().year
    yr = f"{y:04d}"
    def series(sql):
        return {r['m']: r['v'] for r in _all(sql, (yr,))}
    exp_actual = series("SELECT substr(date,6,2) m, SUM(amount) v FROM expenses WHERE status='paid' AND substr(date,1,4)=? GROUP BY m")
    exp_plan   = series("SELECT substr(due_date,6,2) m, SUM(amount) v FROM expenses WHERE status='pending' AND substr(due_date,1,4)=? GROUP BY m")
    inc_actual = series("SELECT substr(COALESCE(NULLIF(received_date,''),due_date),6,2) m, SUM(amount) v FROM income WHERE status='received' AND substr(COALESCE(NULLIF(received_date,''),due_date),1,4)=? GROUP BY m")
    inc_plan   = series("SELECT substr(due_date,6,2) m, SUM(amount) v FROM income WHERE status='pending' AND substr(due_date,1,4)=? GROUP BY m")
    rows = []
    for i in range(1, 13):
        mm = f"{i:02d}"
        rows.append({'m': i,
            'inc_plan': inc_plan.get(mm,0) or 0, 'inc_actual': inc_actual.get(mm,0) or 0,
            'exp_plan': exp_plan.get(mm,0) or 0, 'exp_actual': exp_actual.get(mm,0) or 0})
    return rows

def budget_vs_actual(project_id=None):
    """依工種：預算(合約) vs 實際(已付) vs 差額。"""
    s = _srv(); ph = s._ph()
    pf = ""; params = []
    if project_id:
        pf = f" AND project_id={ph}"; params.append(project_id)
    budget = {r['name']: r['v'] for r in _all(
        f"SELECT c.name, COALESCE(SUM(ct.amount),0) v FROM contracts ct JOIN categories c ON ct.category_id=c.id WHERE 1=1{pf} GROUP BY c.id", params)}
    actual = {r['name']: r['v'] for r in _all(
        f"SELECT c.name, COALESCE(SUM(e.amount),0) v FROM expenses e JOIN categories c ON e.category_id=c.id WHERE e.status='paid'{pf} GROUP BY c.id", params)}
    names = sorted(set(list(budget) + list(actual)), key=lambda n: -(budget.get(n,0)+actual.get(n,0)))
    return [{'name': n, 'budget': budget.get(n,0), 'actual': actual.get(n,0),
             'diff': budget.get(n,0) - actual.get(n,0)} for n in names]

# ── 支出 / 收入 Table（filter/sort/group/search）──────────────────────
def expense_table(f):
    """f = request.args。回傳 (rows, filter_options)。"""
    s = _srv(); ph = s._ph()
    sql = ("SELECT e.*, p.name project_name, v.name vendor_name, c.name trade_name, "
           "ct.amount contract_amount "
           "FROM expenses e "
           "LEFT JOIN projects_v3 p ON e.project_id=p.id "
           "LEFT JOIN vendors_v3 v ON e.vendor_id=v.id "
           "LEFT JOIN categories c ON e.category_id=c.id "
           "LEFT JOIN contracts ct ON e.contract_id=ct.id WHERE 1=1")
    params = []
    if f.get('project'):  sql += f" AND e.project_id={ph}";  params.append(f['project'])
    if f.get('trade'):    sql += f" AND e.category_id={ph}"; params.append(f['trade'])
    if f.get('vendor'):   sql += f" AND e.vendor_id={ph}";   params.append(f['vendor'])
    if f.get('status'):   sql += f" AND e.status={ph}";      params.append(f['status'])
    if f.get('year'):     sql += f" AND substr(e.date,1,4)={ph}"; params.append(f['year'])
    if f.get('month'):    sql += f" AND substr(e.date,6,2)={ph}"; params.append(f"{int(f['month']):02d}")
    if f.get('q'):
        like = f"%{f['q']}%"
        sql += f" AND (e.item LIKE {ph} OR v.name LIKE {ph} OR e.note LIKE {ph})"
        params += [like, like, like]
    sort = {'date':'e.date','amount':'e.amount','vendor':'v.name','trade':'c.name'}.get(f.get('sort',''), 'e.date')
    order = 'ASC' if f.get('order') == 'asc' else 'DESC'
    sql += f" ORDER BY {sort} {order}"
    rows = _all(sql, params)
    # 每筆補：累積付款、剩餘未付（依 contract 聚合）
    paid_by_ct = {r['cid']: r['v'] for r in _all(
        "SELECT contract_id cid, COALESCE(SUM(amount),0) v FROM expenses WHERE status='paid' AND contract_id IS NOT NULL GROUP BY contract_id")}
    for r in rows:
        cid = r.get('contract_id')
        r['paid_cum'] = paid_by_ct.get(cid, 0) if cid else None
        r['remain'] = ((r['contract_amount'] or 0) - r['paid_cum']) if cid else None
    return rows

def income_table(f):
    s = _srv(); ph = s._ph()
    sql = ("SELECT i.*, p.name project_name, c.name type_name "
           "FROM income i LEFT JOIN projects_v3 p ON i.project_id=p.id "
           "LEFT JOIN categories c ON i.type_id=c.id WHERE 1=1")
    params = []
    if f.get('project'): sql += f" AND i.project_id={ph}"; params.append(f['project'])
    if f.get('type'):    sql += f" AND i.type_id={ph}";    params.append(f['type'])
    if f.get('status'):  sql += f" AND i.status={ph}";     params.append(f['status'])
    if f.get('year'):    sql += f" AND substr(COALESCE(NULLIF(i.received_date,''),i.due_date),1,4)={ph}"; params.append(f['year'])
    sort = {'date':'i.due_date','amount':'i.amount'}.get(f.get('sort',''), 'i.due_date')
    order = 'ASC' if f.get('order') == 'asc' else 'DESC'
    sql += f" ORDER BY {sort} {order}"
    return _all(sql, params)

def filter_options():
    return {
        'projects': _all("SELECT id, name FROM projects_v3 ORDER BY name"),
        'trades':   _all("SELECT id, name FROM categories WHERE kind='trade' ORDER BY sort_order, name"),
        'income_types': _all("SELECT id, name FROM categories WHERE kind='income_type' ORDER BY sort_order"),
        'vendors':  _all("SELECT id, name FROM vendors_v3 ORDER BY name"),
        'years':    [r['y'] for r in _all("SELECT DISTINCT substr(date,1,4) y FROM expenses WHERE date<>'' ORDER BY y DESC")],
    }
