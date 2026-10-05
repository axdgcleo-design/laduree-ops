# ── LINE Bot：24 小時接收個人／群組訊息並全部記錄，指令可新增待付款、待辦、缺失 ──
import os, json, hmac, hashlib, base64, threading, re
from datetime import datetime
from types import SimpleNamespace
from flask import Blueprint, request, render_template, send_from_directory, redirect, url_for, abort
import requests as req

bp = Blueprint('line_bot', __name__)
db = SimpleNamespace()   # register() 時由 server.py 注入 fetchall/fetchone/execute/commit

TOKEN   = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
SECRET  = os.environ.get('LINE_CHANNEL_SECRET', '')
ALLOWED = {u.strip() for u in os.environ.get('LINE_ALLOWED_USERS', '').split(',') if u.strip()}
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(BASE_DIR, 'data', 'line_media')

HELP = ("/pay 金額 廠商 備註\n/todo 待辦內容\n/defect 缺失描述\n"
        "私訊傳發票照片 → 自動辨識金額\n/id 查詢自己的 LINE userId\n\n"
        "其他訊息（含群組對話、照片、檔案）都會自動記錄")

EXT = {'image': '.jpg', 'video': '.mp4', 'audio': '.m4a'}

DDL = """
CREATE TABLE IF NOT EXISTS line_chats (
    chat_id TEXT PRIMARY KEY, chat_type TEXT, name TEXT DEFAULT '',
    project_id INTEGER, last_at TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS line_users (
    user_id TEXT PRIMARY KEY, name TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS line_messages (
    id {pk}, message_id TEXT UNIQUE, chat_id TEXT, user_id TEXT DEFAULT '',
    msg_type TEXT, text TEXT DEFAULT '', file_path TEXT DEFAULT '', created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_line_messages_chat ON line_messages (chat_id, created_at)
"""

def register(app, helpers):
    for k, v in helpers.items(): setattr(db, k, v)
    with app.app_context():
        is_pg = 'postgres' in os.environ.get('DATABASE_URL', '')
        pk = 'SERIAL PRIMARY KEY' if is_pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        for stmt in DDL.format(pk=pk).split(';'):
            if stmt.strip(): db.execute(stmt)
        db.commit()
    app.register_blueprint(bp)

# ── LINE API ────────────────────────────────────────────────────────
def _auth(): return {'Authorization': f'Bearer {TOKEN}'}

def reply(reply_token, text):
    req.post('https://api.line.me/v2/bot/message/reply', headers=_auth(), timeout=15,
             json={'replyToken': reply_token, 'messages': [{'type': 'text', 'text': text[:4900]}]})

def _get_json(url):
    try:
        r = req.get(url, headers=_auth(), timeout=10)
        return r.json() if r.ok else {}
    except Exception:
        return {}

def _chat_of(src):
    t = src.get('type', 'user')
    cid = src.get('groupId') or src.get('roomId') or src.get('userId', '')
    return t, cid

def _ensure_chat(src):
    ctype, cid = _chat_of(src)
    if not db.fetchone("SELECT chat_id FROM line_chats WHERE chat_id=?", (cid,)):
        if ctype == 'group':
            name = _get_json(f'https://api.line.me/v2/bot/group/{cid}/summary').get('groupName', '')
        elif ctype == 'user':
            name = _get_json(f'https://api.line.me/v2/bot/profile/{cid}').get('displayName', '')
        else:
            name = '多人聊天'
        db.execute("INSERT INTO line_chats (chat_id,chat_type,name) VALUES (?,?,?)", (cid, ctype, name or cid[:10]))
    return ctype, cid

def _ensure_user(src):
    uid = src.get('userId', '')
    if uid and not db.fetchone("SELECT user_id FROM line_users WHERE user_id=?", (uid,)):
        ctype, cid = _chat_of(src)
        url = {'group': f'https://api.line.me/v2/bot/group/{cid}/member/{uid}',
               'room':  f'https://api.line.me/v2/bot/room/{cid}/member/{uid}'}.get(
               ctype, f'https://api.line.me/v2/bot/profile/{uid}')
        db.execute("INSERT INTO line_users (user_id,name) VALUES (?,?)",
                   (uid, _get_json(url).get('displayName', '') or uid[:10]))
    return uid

def _download(msg, ts):
    data = req.get(f"https://api-data.line.me/v2/bot/message/{msg['id']}/content",
                   headers=_auth(), timeout=120).content
    sub = ts[:7]
    name = msg['id'] + (os.path.splitext(msg.get('fileName', ''))[1] or EXT.get(msg['type'], ''))
    os.makedirs(os.path.join(MEDIA_DIR, sub), exist_ok=True)
    with open(os.path.join(MEDIA_DIR, sub, name), 'wb') as f: f.write(data)
    return f'{sub}/{name}', data

# ── 訊息處理 ─────────────────────────────────────────────────────────
def _ocr(img):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(model='claude-sonnet-4-6', max_tokens=300,
        messages=[{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64.b64encode(img).decode()}},
            {'type': 'text', 'text': '這是發票或收據，只回傳JSON: {"amount":數字,"vendor":"廠商","date":"日期"}'}]}])
    try:
        r = json.loads(re.search(r'\{.*\}', resp.content[0].text, re.S).group(0))
        return (f"📷 辨識結果：\n💰 NT$ {r.get('amount',0):,}\n🏪 {r.get('vendor','')}\n📅 {r.get('date','')}"
                f"\n\n確認後輸入：/pay {r.get('amount',0)} {r.get('vendor','')}")
    except Exception:
        return None

def _command(text, project_id):
    """回傳回覆文字；不是指令則回傳 None。"""
    cmd, _, rest = text.strip().partition(' ')
    cmd, rest = cmd.lower(), rest.strip()
    if cmd in ('/pay', '付款'):
        parts = rest.split(' ', 2)
        try:
            amt = float(parts[0].replace(',', '')); vendor = parts[1]
        except (ValueError, IndexError):
            return "格式：/pay 金額 廠商名稱"
        note = parts[2] if len(parts) > 2 else ''
        db.execute("INSERT INTO vendor_invoices (vendor_name,amount,note,status,project_id) VALUES (?,?,?,'pending',?)",
                   (vendor, amt, note, project_id))
        return f"✅ 待付款已新增\n廠商：{vendor}\n金額：NT$ {amt:,.0f}"
    for keys, ttype, icon in ((('/todo', '待辦'), 'todo', '✅ 待辦'), (('/defect', '缺失'), 'defect', '🔴 缺失')):
        if cmd in keys:
            if not rest: return f"格式：{keys[0]} 內容"
            db.execute("INSERT INTO tasks (title,type,status,source,project_id) VALUES (?,?,'open','line',?)",
                       (rest, ttype, project_id))
            return f"{icon}：{rest}"
    if cmd in ('/help', '說明'): return HELP
    return None

def handle_event(ev):
    src = ev.get('source', {})
    rt = ev.get('replyToken')
    if ev.get('type') == 'join':
        _ensure_chat(src); db.commit()
        reply(rt, "👋 漣一設計工地助理已加入，之後此群組的訊息、照片、檔案會記錄到工程系統。\n輸入 /help 看指令")
        return
    if ev.get('type') != 'message': return

    ctype, cid = _ensure_chat(src)
    uid = _ensure_user(src)
    msg = ev['message']; mtype = msg.get('type')
    ts = datetime.fromtimestamp(ev.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
    text, path, data = msg.get('text', ''), '', None
    if mtype in ('image', 'video', 'audio', 'file'):
        path, data = _download(msg, ts)
        text = msg.get('fileName', '')
    elif mtype == 'sticker':
        text = '[貼圖]'
    elif mtype == 'location':
        text = f"📍 {msg.get('title','')} {msg.get('address','')}".strip()

    db.execute("INSERT INTO line_messages (message_id,chat_id,user_id,msg_type,text,file_path,created_at) VALUES (?,?,?,?,?,?,?)",
               (msg.get('id'), cid, uid, mtype, text, path, ts))
    db.execute("UPDATE line_chats SET last_at=? WHERE chat_id=?", (ts, cid))
    db.commit()

    out = None
    if mtype == 'text' and text.strip().lower() == '/id':
        out = f"你的 LINE userId：\n{uid}"
    elif mtype == 'text' and text.lstrip().startswith(('/', '付款', '待辦', '缺失', '說明')):
        if ALLOWED and uid not in ALLOWED:
            out = "⛔ 你沒有使用指令的權限"
        else:
            proj = db.fetchone("SELECT project_id FROM line_chats WHERE chat_id=?", (cid,))
            out = _command(text, proj and proj['project_id'])
            db.commit()
            if out is None and ctype == 'user': out = HELP
    elif mtype == 'image' and ctype == 'user' and ANTHROPIC_KEY and (not ALLOWED or uid in ALLOWED):
        out = _ocr(data)
    # 群組內一般對話只靜默記錄，不回覆，避免洗版
    if out and rt: reply(rt, out)

def _process(app, events):
    with app.app_context():
        for ev in events:
            try:
                handle_event(ev)
            except Exception as e:
                print(f"LINE event error: {e}", flush=True)

@bp.route('/webhook/line', methods=['POST'])
def webhook():
    from flask import current_app
    body = request.get_data()
    sig = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
    if not SECRET or not hmac.compare_digest(sig, request.headers.get('X-Line-Signature', '')):
        return 'invalid signature', 403
    events = (json.loads(body) or {}).get('events', [])
    if events:   # 立刻回 200 給 LINE，下載檔案／辨識在背景做
        threading.Thread(target=_process, args=(current_app._get_current_object(), events), daemon=True).start()
    return 'ok'

# ── 網頁：查看對話紀錄 ──────────────────────────────────────────────
@bp.route('/line')
def line_messages():
    chats = db.fetchall("""SELECT c.*, p.name AS project_name,
        (SELECT COUNT(*) FROM line_messages m WHERE m.chat_id=c.chat_id) AS n
        FROM line_chats c LEFT JOIN projects p ON c.project_id=p.id ORDER BY c.last_at DESC""")
    cid = request.args.get('chat') or (chats[0]['chat_id'] if chats else '')
    q = request.args.get('q', '').strip()
    sql = """SELECT m.*, u.name AS user_name FROM line_messages m
             LEFT JOIN line_users u ON m.user_id=u.user_id WHERE m.chat_id=?"""
    params = [cid]
    if q: sql += " AND m.text LIKE ?"; params.append(f'%{q}%')
    msgs = list(reversed(db.fetchall(sql + " ORDER BY m.created_at DESC, m.id DESC LIMIT 500", params)))
    projects = db.fetchall("SELECT id,name FROM projects ORDER BY name")
    return render_template('line_messages.html', chats=chats, chat_id=cid, msgs=msgs, q=q, projects=projects)

@bp.route('/line/chat/<chat_id>/project', methods=['POST'])
def line_set_project(chat_id):
    pid = request.form.get('project_id') or None
    db.execute("UPDATE line_chats SET project_id=? WHERE chat_id=?", (pid, chat_id)); db.commit()
    return redirect(url_for('line_bot.line_messages', chat=chat_id))

@bp.route('/line/media/<path:p>')
def line_media(p):
    if '..' in p: abort(404)
    return send_from_directory(MEDIA_DIR, p)
