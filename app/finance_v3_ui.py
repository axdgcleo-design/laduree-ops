# ── Finance v3 UI — Database-First 新頁面（掛在 /v3，與舊頁面並行）─────
import json
from flask import Blueprint, render_template, request
from datetime import date
from app import analytics_v3 as A

bp = Blueprint('finance_v3_ui', __name__)

def _edit_map(rows, fields):
    """把列表整理成 {id: {fields}} 的 JSON，供 Modal 編輯預填。"""
    out = {}
    for r in rows:
        out[r['id']] = {k: r.get(k) for k in fields}
    return json.dumps(out, ensure_ascii=False, default=str)

def fmt(n):
    try: return f'{float(n):,.0f}'
    except: return '0'

@bp.app_template_filter('money')
def _money(n):
    try: return f'{float(n):,.0f}'
    except: return '0'

@bp.route('/v3')
@bp.route('/v3/')
def v3_dashboard():
    y = int(request.args.get('year') or date.today().year)
    m = int(request.args.get('month') or date.today().month)
    return render_template('v3/dashboard.html', active='dashboard',
        d=A.dashboard(y, m), months=A.monthly_series(y),
        trades=A.trade_analysis(y), projects=A.project_rows(),
        cashflow=A.cashflow(y), year=y, month=m, fmt=fmt)

@bp.route('/v3/expenses')
def v3_expenses():
    rows = A.expense_table(request.args)
    group = request.args.get('group') == 'trade'
    grouped = None
    if group:
        grouped = {}
        for r in rows:
            grouped.setdefault(r.get('trade_name') or '未分類', []).append(r)
        grouped = dict(sorted(grouped.items(), key=lambda kv: -sum(x['amount'] for x in kv[1])))
    total = sum(r['amount'] for r in rows)
    edit_map = _edit_map(rows, ('project_id','category_id','vendor_id','item','amount',
        'date','due_date','status','tax_setting','invoice_no','payment_method','note'))
    return render_template('v3/expenses.html', active='expenses',
        rows=rows, grouped=grouped, group=group, total=total,
        opts=A.filter_options(), args=request.args, edit_map=edit_map, fmt=fmt)

@bp.route('/v3/income')
def v3_income():
    rows = A.income_table(request.args)
    total = sum(r['amount'] for r in rows)
    recv = sum(r['amount'] for r in rows if r['status'] == 'received')
    edit_map = _edit_map(rows, ('project_id','type_id','period_no','amount','due_date',
        'received_date','status','tax_setting','bank_account','invoice_no','note'))
    return render_template('v3/income.html', active='income',
        rows=rows, total=total, recv=recv, opts=A.filter_options(),
        args=request.args, edit_map=edit_map, fmt=fmt)

@bp.route('/v3/projects')
def v3_projects():
    return render_template('v3/projects.html', active='projects',
        rows=A.project_rows(), fmt=fmt)

@bp.route('/v3/project/<int:pid>')
def v3_project_detail(pid):
    d = A.project_detail(pid)
    if not d:
        return render_template('v3/base.html', active='projects'), 404
    return render_template('v3/project_detail.html', active='projects', d=d, fmt=fmt)

@bp.route('/v3/vendors')
def v3_vendors():
    from app import server as s
    full = s.fetchall("SELECT * FROM vendors_v3 ORDER BY name")
    trades = s.fetchall("SELECT id, name FROM categories WHERE kind='trade' ORDER BY sort_order, name")
    edit_map = _edit_map(full, ('name','category_id','contact','tel','bank_name',
        'bank_account','bank_holder','tax_id','note'))
    return render_template('v3/vendors.html', active='vendors',
        rows=A.vendor_analysis(), all_vendors=full, trades=trades,
        edit_map=edit_map, fmt=fmt)

@bp.route('/v3/analysis')
def v3_analysis():
    y = int(request.args.get('year') or date.today().year)
    return render_template('v3/analysis.html', active='analysis',
        trades=A.trade_analysis(), vendors=A.vendor_analysis(),
        cashflow=A.cashflow(y), budget=A.budget_vs_actual(),
        year=y, fmt=fmt)

@bp.route('/v3/settings')
def v3_settings():
    from app import server as s
    cats = {}
    for kind in ('trade', 'income_type', 'company_expense'):
        cats[kind] = s.fetchall(
            f"SELECT id, name, active FROM categories WHERE kind={s._ph()} ORDER BY sort_order, name",
            (kind,))
    counts = {t: (s.fetchone(f"SELECT COUNT(*) c FROM {t}") or {}).get('c', 0)
              for t in ('projects_v3', 'income', 'expenses', 'vendors_v3', 'contracts')}
    return render_template('v3/settings.html', active='settings', cats=cats, counts=counts, fmt=fmt)
