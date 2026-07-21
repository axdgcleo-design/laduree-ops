# ── Finance v3 UI — Database-First 新頁面（掛在 /v3，與舊頁面並行）─────
from flask import Blueprint, render_template, request
from datetime import date
from app import analytics_v3 as A

bp = Blueprint('finance_v3_ui', __name__)

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
    return render_template('v3/expenses.html', active='expenses',
        rows=rows, grouped=grouped, group=group, total=total,
        opts=A.filter_options(), args=request.args, fmt=fmt)

@bp.route('/v3/income')
def v3_income():
    rows = A.income_table(request.args)
    total = sum(r['amount'] for r in rows)
    recv = sum(r['amount'] for r in rows if r['status'] == 'received')
    return render_template('v3/income.html', active='income',
        rows=rows, total=total, recv=recv, opts=A.filter_options(),
        args=request.args, fmt=fmt)

@bp.route('/v3/projects')
def v3_projects():
    return render_template('v3/projects.html', active='projects',
        rows=A.project_rows(), fmt=fmt)

@bp.route('/v3/vendors')
def v3_vendors():
    return render_template('v3/vendors.html', active='vendors',
        rows=A.vendor_analysis(), fmt=fmt)

@bp.route('/v3/analysis')
def v3_analysis():
    y = int(request.args.get('year') or date.today().year)
    return render_template('v3/analysis.html', active='analysis',
        trades=A.trade_analysis(), vendors=A.vendor_analysis(),
        cashflow=A.cashflow(y), budget=A.budget_vs_actual(),
        year=y, fmt=fmt)
