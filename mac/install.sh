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

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 2
curl -fs "http://127.0.0.1:$PORT/" >/dev/null && echo "✅ OPS 系統已在背景運作：http://localhost:$PORT" \
  || echo "⚠️ 啟動失敗，請看 $ROOT/logs/ops.log"
