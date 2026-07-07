# 設計: care(kyotaku-navi) → zaitaku-members facilities 接続（第1イテレーション）

- status: draft（第1イテレーション・DB 非接続の接続設計＋seed 生成パイプラインのみ）
- created: 2026-07-07
- scope: 在宅ナビ統合プラットフォーム ロードマップ P1-b「care(kyotaku-navi) を Supabase 統合 → 3業種横断検索」の第1イテレーション
- 依存方向: **kyotaku-navi → zaitaku-members の IF を参照する側（一方向）**。逆依存を作らない。
- PHI: **なし**。個人情報は公開オープンデータ（介護サービス情報公表システム / mhlw 由来）の施設連絡先の範囲に限定。
- 本文書は「設計・契約」のみ。本番/ステージング Supabase への接続・migration 作成・seed 投入は **本イテレーションのスコープ外（人間ゲート）**。

---

## 0. 前提の現物確認（2026-07-07 実走で確定・推測補完なし）

| 対象 | 確認結果 | 確認方法 |
|---|---|---|
| kyotaku-navi HEAD | `16fbb1e32`（validate script 新設）・master・working tree clean | `git log --oneline` |
| 入力データ | `data/normalized/offices_430.json` = **36,491 件**（list） | `json.load` で len |
| `office_id` 一意性 | **完全一意**（unique=36,491・重複0・null/empty 0） | `Counter` 集計 |
| `office_id` 長さ | 全件 **25 文字固定**（例 `mhlw_kaigo:0170102313:430`） | min/max len |
| `is_active` | 全件 `True` | 分布集計 |
| facilities スキーマ | zaitaku-members `supabase/migrations/006_facilities.sql` 実文で確定 | Read |
| `care` allowlist | `src/lib/api-validators.ts` の `ALLOWED_SERVICE_KEYS` に **登録済み** | Read |
| validate_data.py | 実行 exit 0・FAIL=0 WARN=0 OK=8・baseline metrics 変動なし | 実走 |

zaitaku-members は別セッションが working tree を占有中の可能性があるため **読み取り（Read/grep/git log）のみ**実施。IF ファイル（006_facilities.sql / api-validators.ts / 010_consume_claim_token_rpc.sql）は現物 Read で健在を確認した。

---

## 1. マッピング表（offices_430.json → facilities）

接続先 `public.facilities`（006_facilities.sql 実列）:

```
id                    uuid   pk default gen_random_uuid()   -- DB 採番（seed では指定しない）
service_key           text   not null
external_facility_id  text   not null
facility_name         text   not null default ''
postal_code           text
prefecture            text
city                  text
address_line1         text
address_line2         text
created_at            timestamptz not null default now()    -- DB 既定
updated_at            timestamptz not null default now()    -- DB 既定
```

複合一意 index: `uq_facilities_service_external (service_key, external_facility_id)`。
RLS: `select` 全員許可・`insert/update/delete` は admin のみ（本 seed の実投入は admin 権限が前提＝人間ゲート）。

### 1-1. seed に載せるフィールドの対応

| facilities 列 | offices_430.json フィールド | 充足状況（36,491 件中） | 備考 |
|---|---|---|---|
| `service_key` | （固定値 `'care'`） | — | api-validators の allowlist に登録済み |
| `external_facility_id` | `office_id` | 全件・一意・25 文字固定 | 主キー契約。`(service_key, external_facility_id)` 複合一意を満たす |
| `facility_name` | `name` | 全件非 null | — |
| `postal_code` | `postal_code` | **全件 null（36,491 件すべて）** | 現状データに郵便番号なし＝**供給不可**。列は nullable のため seed では null を送る（後述 §5 確認事項） |
| `prefecture` | `prefecture` | 全件非 null | — |
| `city` | `city` | 全件非 null | — |
| `address_line1` | `address` | 全件非 null | 住所本体 |
| `address_line2` | `address_building` | 9,934 件充足 / 26,557 件 null | ビル名。欠損は正常（建物名なし施設）＝null を送る |

`id` / `created_at` / `updated_at` は **DB 側の default に委ねる**（seed で指定しない）。

### 1-2. facilities に載らないフィールド（将来の care_profiles 拡張候補）

`offices_430.json` は 38 フィールドを持つが、facilities は最小の施設同定＋住所のみ。以下は本イテレーションでは seed に含めず、後続の care 詳細プロファイル拡張（仮称 `care_profiles`。clinic_profiles と同型の service_key 別プロファイル層）で扱う候補として明記する（現状 zaitaku-members に care_profiles は未実装＝**確認事項**）:

- 連絡先系: `tel`（36,458 件充足）/ `fax` / `website_url`（21,992 件充足）
- 地理系: `latitude` / `longitude`（**両方全件充足**＝地図表示・近傍検索の資産）
- 法人系: `corporation_number`（35,339 件充足）/ `corporation_name` / `office_code`
- サービス種別: `service_code`（=430）/ `service_name` / `service_category`（=caremanager）/ `portal_type`（=kyotaku）
- 表記系: `name_kana` / `pref_code` / `city_code`
- 運営属性: `business_days_text` / `business_days_note` / `capacity` / `chief_caremanager_count` / `emergency_phone_support` / `terminal_care_addon` / `specific_office_addon` / `inclusive_service` / `meets_kaigo_standard` / `meets_shogai_standard` / `remarks_raw`
- 由来メタ: `is_active`（全件 True）/ `source_primary` / `source_url` / `source_updated_at` / `retrieved_at`

---

## 2. 一意性・件数の契約

- **総件数契約**: 入力 36,491 件 → seed 出力 36,491 件（1:1）。パイプラインが before/after を assert し、不一致は非 0 exit。
- **複合一意契約**: `(service_key='care', external_facility_id=office_id)`。`office_id` は入力側で完全一意（重複 0）を実測確認済み＝複合一意違反は理論上発生しない。万一 dedupe が必要になった場合は差分件数と理由をパイプライン出力に明示する（本イテレーションでは dedupe 0 が期待値）。
- **upsert 契約**: 本番投入時は `on conflict (service_key, external_facility_id) do update`（冪等 upsert）を前提とする。既存 clinic seed（006 の backfill）と同じ複合一意を使うため衝突しない（service_key が異なる）。
- **`is_active` の扱い**: 全件 True。facilities スキーマに `is_active` 列は**存在しない**ため seed には含めない。将来「休止施設の非表示」が必要になった場合は care_profiles 側 or facilities 拡張で扱う（**確認事項**）。

---

## 3. 出力仕様（実装前に確定・推測禁止）

- **JSONL**: `dist/supabase/care_facilities_seed.jsonl`
  - 文字コード: **UTF-8**（BOM なし）
  - 改行: **LF**（`\n`）
  - 1 行 1 レコード。キー = facilities 列名（`service_key` / `external_facility_id` / `facility_name` / `postal_code` / `prefecture` / `city` / `address_line1` / `address_line2`）
  - null は JSON `null` として出力（空文字に変換しない）
- **SQL**（併産・任意投入用）: `dist/supabase/care_facilities_seed.sql`
  - `insert into public.facilities (...) values (...) on conflict (service_key, external_facility_id) do update set ...` の upsert 形式
  - 文字列はパラメータエスケープ（`'` → `''`）。UTF-8 / LF。
  - **このファイルは生成物であり、本イテレーションでは投入しない**（人間ゲート）。

---

## 4. 後続イテレーションの IF 明文化（設計のみ・本イテレーションで実装しない）

1. **seed の本番投入手順案（人間ゲート）**: admin 権限で `care_facilities_seed.sql` を Supabase に upsert 適用。適用は院長 go が必須（facilities の insert/update は RLS で admin 限定）。適用後に `select count(*) from facilities where service_key='care'` = 36,491 を検証。件数 before/after を audit_logs に残す運用を推奨。
2. **care 詳細ページ ⇄ favorites/inquiries/recent_views API**: `target_type='facility'`・`target_id=office_id`・`service_key='care'` で連携。**制約**: `api-validators.ts` の `target_id` は最大 128 文字（office_id は 25 文字固定＝クリア）。care 詳細ページ側は office_id をそのまま target_id として API に渡せる。
3. **claim token（郵送 QR 認証構想）への external_facility_id 供給**: `010_consume_claim_token_rpc.sql` の `consume_facility_claim_token` は facilities(006) + facility_claim_tokens(007) に依存。care 施設が claim 対象になるには facilities に care 行が存在することが前提＝本 seed が供給元になる。トークン発行フロー自体は後続。
4. **更新同期（オープンデータ更新 → facilities upsert）**: 厚労省オープンデータ更新 → `export_supabase_seed.py` 再生成 → upsert（`on conflict do update`）で冪等反映。削除された施設の扱い（論理削除 or 物理削除）は **確認事項**（facilities に is_active 列がないため、care_profiles 側フラグか別途設計が必要）。

---

## 5. 境界規律の宣言（モジュール repo 戦略・バケツ C）

- **依存は一方向**: kyotaku-navi → zaitaku-members の IF を参照する側。逆依存（zaitaku-members が kyotaku-navi を参照）を作らない。zaitaku-members への書き込みは一切しない（read-only 参照のみ）。
- **PHI 有無と分離線の一致**: 本領域は **PHI なし**。seed・設計文書に持ち込む個人情報は公開オープンデータ由来の施設連絡先・法人番号・住所のみに限定し、それ以上（患者情報等）を持ち込まない。
- **乗せ代を保つ**: zaitaku-members が既に用意した共通背骨（facilities / service_key 抽象化 / favorites・inquiries API）に載せるだけ。新たな汎用 layer を切らない。
- **認証・決済・RLS・auth は manual_only（変更禁止）**: 本文書での RLS 記述は 006 実文の引用であり、変更提案・実装はしない。

---

## 6. 確認事項（推測で埋めず後続の人間確認に回す）

- `postal_code` が全件 null＝現状データに郵便番号がない。care 詳細ページや facilities 検索で郵便番号が必要なら、別データソース（住所→郵便番号逆引き等）の補完設計が要る（本イテレーション対象外）。
- zaitaku-members に `care_profiles`（clinic_profiles 相当の care 専用プロファイル層）が現状**存在しない**。§1-2 の拡張候補フィールドを載せるにはスキーマ新設が必要＝後続の zaitaku-members 側イテレーション（別 repo・別 go）。
- 更新同期での「削除施設」の扱い（facilities に is_active 列なし）。
- `latitude`/`longitude` が全件充足＝近傍検索の資産だが facilities に緯度経度列がない。地図・近傍検索を実装するなら facilities 拡張 or care_profiles 設計が要る。
