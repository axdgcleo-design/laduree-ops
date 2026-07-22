# 漣一設計財務系統 — 重構方案（Database First）

> 狀態：Phase 0 進行中。核心決策已與業主確認。
> 平台：沿用 Repo 內 Flask App（SQLite 本地 / Postgres 線上）。
> 原則：以「交易」為中心、字典正規化、所有畫面由核心表 `GROUP BY` 即時算出，不重複儲存。

## 已確認決策
1. **加一張 `contracts`（發包合約）表** — 合約金額只存一處，累積付款／剩餘未付／預算 vs 實際全部算出來。
2. **在既有 Flask App 上重構** — 沿用已部署環境，把舊資料 migration 進來。
3. **先做 Phase 0（Schema + Migration + 對帳）** — 先把地基與資料搬遷做對、對帳無誤，再逐階段換 UI。

---

## 1. 目前架構問題診斷

核心病灶：資料模型「以合約／期數為中心」，不是「以交易為中心」。

1. 支出被切成 4 張表（vendor_contracts / vendor_payments / vendor_invoices / company_expenses / purchases），同一筆花錢散落多處。
2. 收入分裂：業主請款在 invoice_periods、追加在 extra_works、退款無統一位置。
3. 「一個工種一張 Card」是資料結構造成的（renderProjDetail 逐 vendor_contract render），案件多就無限下滑。
4. 工種是自由字串 → 木工/木作/木工程 被當成三種東西，無法統計。
5. 廠商付款不強制關聯 vendor_id（存字串），廠商合作總額算不出來。
6. 沒有分析層（月份維度、現金流、預算 vs 實際）。
7. 金額重複儲存（合約/累積/剩餘都當欄位存），改一處要同步多處。

---

## 2. 新資料架構（Schema）

核心：`categories` `vendors` `projects` `income` `expenses` + `contracts`（建議加）。
非核心保留：`company_info`，以及 `tasks` / `site_photos`（工地模組，與財務無關，不動）。

### categories（字典：工種 / 收入類型 / 公司費用類別）
```
id PK
kind        'trade' | 'income_type' | 'company_expense'
name        木工 / 設計費 / 房租…
sort_order  int
color       圖表用（可選）
active      1/0
```

### vendors（廠商）
```
id PK, name, category_id FK→categories(trade), contact, tel,
bank_name, bank_account, bank_holder, tax_id(統編), note, active, created_at
```

### projects（只存合約本體，其餘計算得出）
```
id PK, code, name, client_name, client_tel, client_email, address,
status  'lead'(設計中)|'active'(施工中)|'completed'(完工)|'paused'|'archived',
start_date, end_date,
design_fee, construction_contract,
note, created_at, updated_at
```
計算欄位（不入庫）：
| 欄位 | 公式 |
|---|---|
| 追加 / 減項 | Σ income WHERE type=追加款 / 減項 |
| 工程總價 | design_fee + construction_contract + 追加 − 減項 |
| 已收 / 未收 | Σ income status=received / pending |
| 已付 / 未付 | Σ expenses status=paid / pending |
| 實際成本 | Σ expenses（該專案） |
| 預估成本 | Σ contracts.amount（該專案） |
| 毛利 / 毛利率 | 收入 − 實際成本 ／ 毛利 ÷ 收入 |

### income（統一所有進帳）
```
id PK, project_id FK, date, due_date(預計/應收),
period_no, type_id FK→categories(income_type),
amount, tax_setting, bank_account,
status 'pending'|'received', received_date,
invoice_no, note, created_at
```

### expenses（統一所有出帳，取代舊 4 表）
```
id PK, project_id FK(NULL=公司營運), category_id FK→categories(trade),
vendor_id FK→vendors, contract_id FK→contracts(可NULL),
item, amount(本次付款), date, due_date(應付),
status 'pending'|'paid', tax_rate, invoice_no, payment_method, note, created_at
```
累積付款 / 剩餘未付：對 contract_id GROUP BY，不儲存。

### contracts（發包合約）
```
id PK, project_id FK, vendor_id FK, category_id FK,
amount(合約金額), signed_date, note, created_at
```
- 累積付款 = Σ expenses(contract_id=X, status=paid)
- 剩餘未付 = contracts.amount − 累積付款
- 預算 vs 實際 = contracts.amount vs Σexpenses
- 專案預估成本 = Σ contracts.amount

---

## 3. API 規劃（Flask Blueprints）
```
/api/projects   /api/project/<id>
/api/income     /api/income/<id>
/api/expenses   /api/expense/<id>
/api/contracts  /api/contract/<id>
/api/vendors    /api/vendor/<id>
/api/categories /api/category/<id>

/api/analytics/dashboard?month=&year=
/api/analytics/projects
/api/analytics/trades?year=
/api/analytics/vendors?year=
/api/analytics/cashflow?year=
/api/analytics/budget?project_id=

/api/backup  /api/restore
/api/migrate-legacy （Phase 0：匯入舊 JSON + 對帳）
```
income / expenses 的 GET 共用 query：project_id, category_id, vendor_id, year, month, status, q, group_by, sort。

---

## 4. Component 規劃（Flask + Jinja + vanilla JS，維持無 build、PWA 離線）
- DataTable（搜尋/排序/Filter/Group by 工種，收入與支出共用）
- FilterBar（專案・工種・廠商・年・月・已付未付・已收未收）
- KpiCard（Dashboard 12 格）
- Chart（Chart.js，vendored 進 static 維持離線）
- EntryModal / CategorySelect / VendorSelect

---

## 5. 頁面架構
```
/            Dashboard（12 KPI + 6 圖表）
/projects    專案列表（Table）
/project/<id> 專案 detail（收入/支出/合約/毛利摘要）
/income      收入 Table
/expenses    支出 Table（可 group by 工種）★取代逐工種 Card
/vendors     廠商主檔 + 分析
/categories  字典維護
/analysis    工種 / 廠商 / 現金流 / 預算vs實際
/settings    公司抬頭・備份・雲端
(/tasks, /site-photos 保留)
```

---

## 6. Migration 方案（保留舊資料）
支援兩種來源格式：localStorage 版（camelCase）與 Flask v2.0 備份。

| 舊 | → 新 | 規則 |
|---|---|---|
| projects | projects | status 中文→enum；designContract→design_fee |
| periods / invoice_periods | income | 工程費→工程款、設計費→設計費；已收→received |
| vendor-contracts | contracts | category 字串→比對/建立 categories |
| vendor-payments / vendor_invoices | expenses | vendorContractId→contract_id；vendorName→vendors.id |
| extra-works | income（追加款/減項） | type 判斷 |
| purchases | expenses（工種=材料/採購） | |
| company-expenses | expenses（project_id=NULL） | |
| vendors | vendors + 自動建 categories | |
| pending-payments / invoice-inbox | 對應 pending，或保留 inbox | |

安全機制：舊表不刪、新表並行；migration 冪等（legacy_id 去重）；匯入前 /api/backup 全量備份；產出「新舊總額對帳表」一致才切換。

---

## 7. 重構順序
- Phase 0 — Schema + Migration + 對帳（不動 UI）← 目前
- Phase 1 — Expenses Table（解決下滑）
- Phase 2 — Income Table
- Phase 3 — Vendors + Categories 字典化
- Phase 4 — Project Detail 改版
- Phase 5 — Dashboard
- Phase 6 — Analysis 中心
- Phase 7 — 收尾（舊路由導向、備份 v3）

---

## 8. ERP 加值建議
- 請款排程與催收（income.due_date → 本週該收/逾期）
- 發包對帳表（合約 vs 已付 vs 剩餘，發款前防超付）
- 毛利即時預警（實際成本/合約收入 超閾值標紅）
- 廠商評比（案數/結案週期/追加頻率）
- 稅務概算延續（接新 income/expenses.tax_setting）
- Telegram 拍照辨識發票 → 直接寫入 expenses(pending)
- 未來：users + audit_log 權限；3 個月現金流預測
