# 照片整理助手（原生 iOS App）

一支**完全本地**的 iPhone 照片分類 App：自動讀取你整本相簿、依「工地（案場 → 工種）」與「個人（想買 / 截圖 / 收據…）」分類，並用**手機本地 AI**（Apple Vision，照片不上雲）自動建議分類。

照片本身不會被複製或上傳——只在 App 裡記錄每張照片的分類標籤（存成一個本機 JSON）。

---

## 架構

- `Sources/App.swift` — App 進入點
- `Sources/Models.swift` — 資料模型（Tagging / Project）＋本地儲存 Store
- `Sources/PhotoLibrary.swift` — PhotoKit 讀取相簿
- `Sources/AssetImage.swift` — 縮圖、格狀、模式切換元件
- `Sources/AIClassifier.swift` — 本地 AI 判斷（截圖 / 收據 / 生活照 / 工地空間）
- `Sources/ClassifySheet.swift` — 單張分類編輯 + AI 建議
- `Sources/RootView.swift` — 權限畫面 + 底部四分頁
- `Sources/SitesView.swift` — 案場 / 分類卡片 + 群組照片
- `Sources/OrganizeView.swift` — 未分類 + AI 批次建議
- `Sources/TimelineSearchView.swift` — 時間軸 + 搜尋

需求：**Xcode 15 或以上**、iOS 16 以上的 iPhone。

---

## 怎麼裝到你的 iPhone（兩種方式，挑一種）

### 方式 A：手動建立專案（最保險，約 5 分鐘，不用裝任何東西）

1. 打開 **Xcode → File → New → Project → iOS → App → Next**。
2. Product Name 填 `PhotoSorter`、Interface 選 **SwiftUI**、Language 選 **Swift**，其他預設，存到任意位置。
3. 在左側檔案列表，把 Xcode 自動產生的 **`ContentView.swift`** 和 **`PhotoSorterApp.swift`** 刪掉（Move to Trash）。
4. 把本資料夾 `Sources/` 裡的 **所有 `.swift` 檔**一起拖進 Xcode 專案；跳出視窗勾選 **Copy items if needed**、並確認 **Add to target: PhotoSorter**。
5. 設定相簿權限文字：點最上方藍色專案 → TARGETS 的 PhotoSorter → **Info** 分頁 → 在列表空白處按 ＋，新增
   - Key：`Privacy - Photo Library Usage Description`
   - Value：`用來讀取相簿照片並分類，照片不會離開你的手機。`
6. 設定簽章：**Signing & Capabilities** 分頁 → **Team** 選你的 Apple ID（沒有的話 Xcode → Settings → Accounts → ＋ 加入你的 Apple ID 即可，免付費）。若 Bundle Identifier 顯示紅字衝突，改成獨一無二的字串，例如 `com.你的名字.photosorter`。
7. 用線接上 iPhone，Xcode 上方裝置選你的 iPhone，按 **▶︎ Run**。
8. 第一次會失敗並提示「不受信任的開發者」——到 iPhone **設定 › 一般 › VPN 與裝置管理** → 點你的 Apple ID → **信任**，再回 Xcode 按一次 Run。
9. App 打開後按「讀取相簿」，允許存取 → 開始分類。

> 免付費 Apple ID 的 App 每 7 天需要重新用 Xcode Run 一次（Apple 限制）；想長期免重簽、或上架，需要加入付費的 Apple Developer Program。

### 方式 B：用 XcodeGen 自動產生專案（給熟 terminal 的人，一行指令）

```bash
brew install xcodegen          # 若尚未安裝
cd ios/PhotoSorter
xcodegen generate              # 產生 PhotoSorter.xcodeproj
open PhotoSorter.xcodeproj     # 開啟後，照方式 A 的第 6～9 步設定簽章並 Run
```

---

## 目前版本（v1）做到什麼

- ✅ 自動讀取整本相簿（PhotoKit），縮圖格狀、依日期時間軸
- ✅ 工地 / 個人雙模式；工地分「案場 → 依工種」；個人分「分類」
- ✅ 點任一照片即可分類（案場 / 空間 / 工種 或 個人分類 / 最愛）
- ✅ 本地 AI 建議：**截圖**（PhotoKit 內建旗標，最準）、**文件/收據**（文字密度）、**餐飲/寵物/風景**（Vision 影像標籤）、工地照片嘗試猜**空間**
- ✅ 「整理」頁一鍵批次 AI 建議；搜尋（空間/工種/分類/案場）

## 已知限制（誠實說）

- 本地 AI 能可靠分出「截圖/收據/生活照」，但**精細工種（水電 vs 木作）靠通用模型判斷不準**，v1 以建議空間 + 由你確認為主。要更準可之後：(a) 用 Create ML 拿你標好的照片訓練專屬模型，或 (b) 改用雲端 Claude 視覺（較準但會上傳照片）。
- 案場（哪個工地）AI 無法從畫面得知，需由你指定。
- 照片量很大時，首次捲動縮圖載入會需要一點時間（已用系統快取與延遲載入）。
