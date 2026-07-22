# ── Finance v3 寫入 API（新增/編輯/刪除）─────────────────────────────
# JSON REST，供 /v3 各頁的 Modal 呼叫。全部走 app.server 的 DB helper。
from flask import Blueprint, request, jsonify
from datetime import date

bp = Blueprint('finance_v3_api', __name__)

def _srv():
    from app import server as s
    return s

def _f(v, d=0.0):
    try: return float(v)
    except (TypeError, ValueError): return d

def _patch(table, allowed, rid, data):
    """通用 PATCH：只更新 allowed 內、且有出現在 data 的欄位。"""
    s = _srv(); ph = s._ph()
    fields, vals = [], []
    for k in allowed:
        if k in data:
            fields.append(f"{k}={ph}"); vals.append(data[k])
    if not fields:
        return jsonify({'ok': False, 'error': 'no fields'})
    vals.append(rid)
    s.execute(f"UPDATE {table} SET {','.join(fields)} WHERE id={ph}", vals)
    s.commit()
    return jsonify({'ok': True})

def _del(table, rid):
    s = _srv(); ph = s._ph()
    s.execute(f"DELETE FROM {table} WHERE id={ph}", (rid,))
    s.commit()
    return jsonify({'ok': True})

# ── 支出 expenses ─────────────────────────────────────────────────────
EXPENSE_FIELDS = ('project_id','category_id','vendor_id','contract_id','item',
                  'amount','date','due_date','status','tax_setting','tax_rate',
                  'invoice_no','payment_method','note')

@bp.route('/api/v3/expense', methods=['POST'])
def expense_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    s.execute(f"""INSERT INTO expenses
        (project_id,category_id,vendor_id,contract_id,item,amount,date,due_date,
         status,tax_setting,invoice_no,payment_method,note)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        (d.get('project_id') or None, d.get('category_id') or None,
         d.get('vendor_id') or None, d.get('contract_id') or None, d.get('item',''),
         _f(d.get('amount')), d.get('date',''), d.get('due_date',''),
         d.get('status','paid'), d.get('tax_setting',''), d.get('invoice_no',''),
         d.get('payment_method',''), d.get('note','')))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/expense/<int:rid>', methods=['PATCH'])
def expense_update(rid):
    return _patch('expenses', EXPENSE_FIELDS, rid, request.json or {})

@bp.route('/api/v3/expense/<int:rid>', methods=['DELETE'])
def expense_delete(rid):
    return _del('expenses', rid)

# ── 收入 income ───────────────────────────────────────────────────────
INCOME_FIELDS = ('project_id','type_id','period_no','amount','date','due_date',
                 'status','received_date','tax_setting','bank_account','invoice_no','note')

@bp.route('/api/v3/income', methods=['POST'])
def income_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    s.execute(f"""INSERT INTO income
        (project_id,type_id,period_no,amount,date,due_date,status,received_date,
         tax_setting,bank_account,invoice_no,note)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        (d.get('project_id') or None, d.get('type_id') or None,
         int(d.get('period_no') or 1), _f(d.get('amount')), d.get('date',''),
         d.get('due_date',''), d.get('status','pending'), d.get('received_date',''),
         d.get('tax_setting','未稅'), d.get('bank_account',''), d.get('invoice_no',''),
         d.get('note','')))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/income/<int:rid>', methods=['PATCH'])
def income_update(rid):
    return _patch('income', INCOME_FIELDS, rid, request.json or {})

@bp.route('/api/v3/income/<int:rid>', methods=['DELETE'])
def income_delete(rid):
    return _del('income', rid)

@bp.route('/api/v3/income/<int:rid>/receive', methods=['POST'])
def income_receive(rid):
    """標記已收 / 取消已收。"""
    s = _srv(); ph = s._ph(); d = request.json or {}
    if d.get('received', True):
        rd = d.get('received_date') or date.today().isoformat()
        s.execute(f"UPDATE income SET status='received', received_date={ph} WHERE id={ph}", (rd, rid))
    else:
        s.execute(f"UPDATE income SET status='pending', received_date='' WHERE id={ph}", (rid,))
    s.commit()
    return jsonify({'ok': True})

# ── 支出：標記已付 / 未付 ─────────────────────────────────────────────
@bp.route('/api/v3/expense/<int:rid>/pay', methods=['POST'])
def expense_pay(rid):
    s = _srv(); ph = s._ph(); d = request.json or {}
    if d.get('paid', True):
        dt = d.get('date') or date.today().isoformat()
        s.execute(f"UPDATE expenses SET status='paid', date={ph} WHERE id={ph}", (dt, rid))
    else:
        s.execute(f"UPDATE expenses SET status='pending' WHERE id={ph}", (rid,))
    s.commit()
    return jsonify({'ok': True})

# ── 廠商 vendors_v3 ───────────────────────────────────────────────────
VENDOR_FIELDS = ('name','category_id','contact','tel','bank_name','bank_account',
                 'bank_holder','tax_id','note','active')

@bp.route('/api/v3/vendor', methods=['POST'])
def vendor_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    if not (d.get('name') or '').strip():
        return jsonify({'ok': False, 'error': 'name required'}), 400
    s.execute(f"""INSERT INTO vendors_v3
        (name,category_id,contact,tel,bank_name,bank_account,bank_holder,tax_id,note)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        (d['name'].strip(), d.get('category_id') or None, d.get('contact',''),
         d.get('tel',''), d.get('bank_name',''), d.get('bank_account',''),
         d.get('bank_holder',''), d.get('tax_id',''), d.get('note','')))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/vendor/<int:rid>', methods=['GET'])
def vendor_get(rid):
    s = _srv(); ph = s._ph()
    return jsonify(s.fetchone(f"SELECT * FROM vendors_v3 WHERE id={ph}", (rid,)) or {})

@bp.route('/api/v3/vendor/<int:rid>', methods=['PATCH'])
def vendor_update(rid):
    return _patch('vendors_v3', VENDOR_FIELDS, rid, request.json or {})

@bp.route('/api/v3/vendor/<int:rid>', methods=['DELETE'])
def vendor_delete(rid):
    return _del('vendors_v3', rid)

@bp.route('/api/v3/vendor/merge', methods=['POST'])
def vendor_merge():
    """把 from_ids 的支出/合約改掛到 to_id，再刪除 from 廠商。"""
    s = _srv(); ph = s._ph(); d = request.json or {}
    to_id = d.get('to_id')
    from_ids = [x for x in (d.get('from_ids') or []) if str(x) != str(to_id)]
    if not to_id or not from_ids:
        return jsonify({'ok': False, 'error': 'need to_id and from_ids'}), 400
    moved = 0
    for fid in from_ids:
        s.execute(f"UPDATE expenses  SET vendor_id={ph} WHERE vendor_id={ph}", (to_id, fid))
        s.execute(f"UPDATE contracts SET vendor_id={ph} WHERE vendor_id={ph}", (to_id, fid))
        s.execute(f"DELETE FROM vendors_v3 WHERE id={ph}", (fid,))
        moved += 1
    s.commit()
    return jsonify({'ok': True, 'merged': moved})

# ── 工種 / 類型字典 categories ────────────────────────────────────────
@bp.route('/api/v3/category', methods=['POST'])
def category_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'}), 400
    kind = d.get('kind', 'trade')
    exists = s.fetchone(f"SELECT id FROM categories WHERE kind={ph} AND name={ph}", (kind, name))
    if exists:
        return jsonify({'ok': True, 'id': exists['id']})
    s.execute(f"INSERT INTO categories (kind,name,sort_order) VALUES ({ph},{ph},{ph})",
              (kind, name, int(d.get('sort_order') or 500)))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/category/<int:rid>', methods=['PATCH'])
def category_update(rid):
    return _patch('categories', ('name','sort_order','active'), rid, request.json or {})

@bp.route('/api/v3/category/<int:rid>', methods=['DELETE'])
def category_delete(rid):
    return _del('categories', rid)

# ── 專案 projects_v3 ──────────────────────────────────────────────────
PROJECT_FIELDS = ('name','client_name','client_tel','client_email','address',
                  'status','start_date','end_date','design_fee','construction_contract','note')

def _next_code():
    s = _srv()
    row = s.fetchone("SELECT code FROM projects_v3 WHERE code LIKE 'P-%' ORDER BY id DESC LIMIT 1")
    if not row or not row.get('code'):
        return 'P-001'
    try: n = int(row['code'].split('-')[1]) + 1
    except Exception: n = 1
    return f'P-{n:03d}'

@bp.route('/api/v3/project', methods=['POST'])
def project_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    if not (d.get('name') or '').strip():
        return jsonify({'ok': False, 'error': 'name required'}), 400
    s.execute(f"""INSERT INTO projects_v3
        (code,name,client_name,client_tel,client_email,address,status,start_date,
         end_date,design_fee,construction_contract,note)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        (_next_code(), d['name'].strip(), d.get('client_name',''), d.get('client_tel',''),
         d.get('client_email',''), d.get('address',''), d.get('status','active'),
         d.get('start_date',''), d.get('end_date',''), _f(d.get('design_fee')),
         _f(d.get('construction_contract')), d.get('note','')))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/project/<int:rid>', methods=['PATCH'])
def project_update(rid):
    return _patch('projects_v3', PROJECT_FIELDS, rid, request.json or {})

@bp.route('/api/v3/project/<int:rid>', methods=['DELETE'])
def project_delete(rid):
    return _del('projects_v3', rid)

# ── 發包合約 contracts ────────────────────────────────────────────────
@bp.route('/api/v3/contract', methods=['POST'])
def contract_add():
    s = _srv(); ph = s._ph(); d = request.json or {}
    s.execute(f"""INSERT INTO contracts (project_id,vendor_id,category_id,amount,signed_date,note)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph})""",
        (d.get('project_id') or None, d.get('vendor_id') or None,
         d.get('category_id') or None, _f(d.get('amount')),
         d.get('signed_date',''), d.get('note','')))
    s.commit()
    return jsonify({'ok': True, 'id': s.last_insert_id()})

@bp.route('/api/v3/contract/<int:rid>', methods=['PATCH'])
def contract_update(rid):
    return _patch('contracts', ('project_id','vendor_id','category_id','amount','signed_date','note'),
                  rid, request.json or {})

@bp.route('/api/v3/contract/<int:rid>', methods=['DELETE'])
def contract_delete(rid):
    return _del('contracts', rid)
