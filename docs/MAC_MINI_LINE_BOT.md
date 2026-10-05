# Mac mini 24 小時 LINE Bot 設定

讓 Mac mini 一直開著跑 OPS 系統，LINE 傳來的訊息隨時都會被接收並寫進系統。

```
手機 LINE ──> LINE 伺服器 ──HTTPS──> Tailscale Funnel ──> Mac mini :5006 /webhook/line
```

只有 `/webhook/line` 這一個路徑會對外公開，財務頁面仍然只有自己家／辦公室網路看得到。

## Bot 會做什麼

**全部記錄**：不論是私訊或群組，文字（長訊息也完整保存）、照片、影片、語音、檔案都會存進系統，可以在網頁上的「LINE 紀錄」頁面依對話查看、搜尋。每個群組都可以對應一個案場。

| 傳給 Bot | 結果 |
|---|---|
| 一般對話、照片、檔案 | 靜默記錄（群組裡不會回話洗版） |
| `/pay 12000 木工 備註`（或 `付款 12000 木工`） | 新增待付款（群組有對應案場會自動帶入） |
| `/todo 叫料`（或 `待辦 叫料`） | 新增待辦 |
| `/defect 牆面裂縫`（或 `缺失 牆面裂縫`） | 新增缺失 |
| 私訊傳發票照片 | Claude 辨識金額／廠商／日期 |
| `/id` | 回傳你的 LINE userId |

> **LINE 的限制**：Bot 只看得到「傳給 Bot 的私訊」和「Bot 有加入的群組」。
> 你和別人一對一的私人聊天，Bot 讀不到。想記錄工地群組，就把 Bot 邀請進該群組。

---

## 1. 讓 Mac mini 永不睡眠（最重要）
**螢幕可以關，但主機不能睡**。主機睡著以後網路會斷，LINE 訊息就收不到了。
`mac/install.sh` 會自動處理這件事：
- `pmset`：關閉睡眠、停電恢復後自動開機、允許網路喚醒
- 背景常駐 `caffeinate`：就算有人改了能源設定，也會擋住睡眠

另外要手動做兩件事：
- 系統設定 → 使用者與群組 → 開啟**自動登入**（重開機後服務才會自己啟動）
- 盡量**插網路線**，Wi-Fi 比較容易斷線

## 2. 下載程式
```bash
xcode-select --install          # 第一次用 git 才需要
cd ~ && git clone https://github.com/axdgcleo-design/laduree-ops.git
```

## 3. 建立 LINE Messaging API Channel
1. 到 <https://developers.line.biz/console/> 建立 Provider，再建立 **Messaging API** channel。
2. **Basic settings** 頁面：複製 **Channel secret**。
3. **Messaging API** 頁面：
   - 最下面的 **Channel access token** 按 Issue，然後複製。
   - **Allow bot to join group chats** 改成 Enabled（才能拉進工地群組）。
   - **Auto-reply messages** 和 **Greeting messages** 都關掉（到 LINE Official Account Manager 設定）。
   - 用手機掃 QR code，把 bot 加為好友。

## 4. 安裝並啟動
```bash
cd ~/laduree-ops
bash mac/install.sh      # 第一次執行會建立 .env 並自動打開
```
在 `.env` 填入 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`ANTHROPIC_KEY`，存檔後**再執行一次** `bash mac/install.sh`。
看到「✅ OPS 系統已在背景運作」就完成了。之後開機會自動啟動，當掉也會自動重啟。

> **資料存哪裡？** `DATABASE_URL` 留空會寫進 Mac mini 本機的 `data/ops.db`。
> 如果要繼續用 Railway 上的資料，就把 Railway Postgres 的 **public** 連線網址填進去。

## 5. 對外開放 webhook（Tailscale Funnel，免費、網址固定）
1. 從 <https://tailscale.com/download/mac> 下載安裝 **Standalone** 版（不是 App Store 版），然後登入。
2. 在 Tailscale 管理後台開啟 Funnel（第一次執行下面的指令時，會跳出網址引導你開啟）。
3. 終端機執行：
   ```bash
   tailscale funnel --bg --set-path /webhook/line http://127.0.0.1:5006/webhook/line
   tailscale funnel status     # 會顯示 https://<機器名>.<tailnet>.ts.net/webhook/line
   ```
   `--bg` 會讓 Funnel 一直開著，重開機後也不用重設。

## 6. 把網址填到 LINE
LINE Developers → Messaging API → **Webhook URL** 填入：
`https://<機器名>.<tailnet>.ts.net/webhook/line`
→ 按 **Verify**（成功會顯示 Success）→ 開啟 **Use webhook**。

## 7. 鎖定只有自己能用
在 LINE 傳 `/id` 給 bot，把回傳的 userId 填進 `.env`：
```
LINE_ALLOWED_USERS=Uxxxxxxxxxxxxxxxx
```
多個人用逗號分隔。改完執行 `mac/update.command` 重新啟動。
設定之後，**只有名單上的人可以下指令**（新增待付款／待辦／缺失）；群組裡其他人（例如師傅）的對話還是會照常記錄。

## 8. 邀請 Bot 進工地群組
在 LINE 群組 → 邀請 → 選擇你的 Bot。Bot 加入時會在群組裡發一則公告，告知大家「訊息會被記錄」。
接著到網頁「LINE 紀錄」→ 選擇該群組 → 右上角選「對應案場」。

---

## 日常操作
- **更新程式**：雙擊 `mac/update.command`（第一次可能要按右鍵 → 打開）
- **查看狀態和紀錄**：雙擊 `mac/status.command`，可以看到服務、防睡眠是否正常，完整紀錄在 `logs/ops.log`
- **照片／檔案存放位置**：`data/line_media/`（建議用時光機備份整台 Mac mini）
- **辦公室電腦開系統**：`http://<Mac mini 的 IP>:5006`（IP 在 系統設定 → 網路 查）
