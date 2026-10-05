#!/bin/bash
# 雙擊執行：查看服務狀態與最近的紀錄
cd "$(dirname "$0")/.."
launchctl print "gui/$(id -u)/com.lianyi.ops" | grep -E "state|pid" | head -3
echo "--- 防睡眠 ---"; pmset -g | grep -E " sleep|autorestart"; pmset -g assertions | grep -c caffeinate | sed "s/^/caffeinate 運作中: /"
echo "--- 最近紀錄 ---"; tail -20 logs/ops.log
read -n 1 -p "按任意鍵關閉"
