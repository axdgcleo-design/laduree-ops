#!/bin/bash
# Mac mini 一次性安裝：建立 Python 環境、設定開機自動啟動（launchd，當掉會自動重啟）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.lianyi.ops"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
cd "$ROOT"

[ -f .env ] || { cp .env.example .env; echo "已建立 .env，請先填入 LINE 金鑰後再執行一次"; open -e .env; exit 0; }

python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p logs

PORT=$(grep -E '^PORT=' .env | cut -d= -f2); PORT=${PORT:-5006}
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key><array>
    <string>$ROOT/.venv/bin/gunicorn</string><string>app.server:app</string>
    <string>--bind</string><string>0.0.0.0:$PORT</string>
    <string>--workers</string><string>2</string><string>--timeout</string><string>120</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/logs/ops.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/ops.log</string>
</dict></plist>
PL

# 防睡眠：螢幕可以關，但主機不能睡（睡著就收不到 LINE）
AWAKE_PLIST="$HOME/Library/LaunchAgents/$LABEL.awake.plist"
cat > "$AWAKE_PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL.awake</string>
  <key>ProgramArguments</key><array><string>/usr/bin/caffeinate</string><string>-ims</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
PL

echo "設定電源：永不睡眠、停電恢復自動開機（需要輸入 Mac 登入密碼）"
sudo pmset -a sleep 0 disksleep 0 autorestart 1 womp 1 tcpkeepalive 1 powernap 0 || echo "⚠️ 電源設定未完成，請到 系統設定 → 能源 手動設定"

for P in "$PLIST" "$AWAKE_PLIST"; do
  L=$(basename "$P" .plist)
  launchctl bootout "gui/$(id -u)/$L" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$P"
done
sleep 2
curl -fs "http://127.0.0.1:$PORT/" >/dev/null && echo "✅ OPS 系統已在背景運作：http://localhost:$PORT" \
  || echo "⚠️ 啟動失敗，請看 $ROOT/logs/ops.log"
