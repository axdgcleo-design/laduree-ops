#!/bin/bash
# 雙擊執行：從 GitHub 拉最新版本並重啟服務
cd "$(dirname "$0")/.."
git pull --ff-only && .venv/bin/pip install -q -r requirements.txt
launchctl kickstart -k "gui/$(id -u)/com.lianyi.ops" && echo "✅ 已更新並重新啟動"
read -n 1 -p "按任意鍵關閉"
