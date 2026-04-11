# 居宅介護支援事業所ポータル データ設計

## 1. 概要

### 目的
全国の居宅介護支援事業所（ケアマネジャーの所属事業所）を網羅したポータルサイトを構築する。
ケアマネジャーや患者・利用者家族が近隣の事業所を探せる静的サイトとして実装する。

### 規模感
- 総件数: **36,491件**（全国47都道府県、2025年時点）
- 緯度/経度: **100%充填**（地図表示が即座に可能）
- 電話番号: **100%充填**
- カナ: **100%充填**

### 兄弟プロジェクトとの関係
| プロジェクト | サービスコード | 件数 | ステータス |
|---|---|---|---|
| 訪問診療ナビ (zaitaku-clinic-navi) | — | 15,759件 | 稼働中 |
| 訪問看護ナビ (houmonkango-navi) | 130 | 未確認 | 構築中 |
| **居宅介護支援ナビ (kyotaku-navi)** | 430 | 36,491件 | 設計中 |

---

## 2. データ取得元

### 2.1 主データソース

**厚生労働省オープンデータ — jigyosho_430.csv**

| 項目 | 内容 |
|---|---|
| URL | https://www.mhlw.go.jp/content/12300000/jigyosho_430.csv |
| ライセンス | CC BY 4.0（出典明記で商用利用可） |
| 文字コード | UTF-8 BOM付き (utf-8-sig) |
| 更新頻度 | 年2回（6月末・12月末） |
| 総件数 | 36,491件 |
| カラム数 | 24列 |

**カラム一覧（全24列）**

| 列 | カラム名 | 充填率 | 備考 |
|---|---|---|---|
| 0 | 都道府県コード又は市町村コード | 100% | 6桁の市区町村コード |
| 1 | No | 100% | 事業所番号（列15と同値） |
| 2 | 都道府県名 | 100% | |
| 3 | 市区町村名 | 100% | |
| 4 | 事業所名 | 100% | |
| 5 | 事業所名カナ | 100% | |
| 6 | サービスの種類 | 100% | 固定値「居宅介護支援」 |
| 7 | 住所 | 100% | 都道府県含む全文 |
| 8 | 方書（ビル名等） | — | 空欄が多い |
| 9 | 緯度 | 100% | WGS84 |
| 10 | 経度 | 100% | WGS84 |
| 11 | 電話番号 | 100% | ハイフン付き |
| 12 | FAX番号 | 99.2% | |
| 13 | 法人番号 | 96.8% | 13桁 |
| 14 | 法人の名称 | 99.4% | |
| 15 | 事業所番号 | 100% | 10桁。主キーとして使用 |
| 16 | 利用可能曜日 | — | 「平日」等 |
| 17 | 利用可能曜日特記事項 | — | |
| 18 | 定員 | — | 0は未記入扱い |
| 19 | URL | 65.1% | メールアドレス混入あり→要バリデーション |
| 20 | 共生型サービス | — | |
| 21 | 介護保険基準充足 | — | |
| 22 | 障害福祉基準充足 | — | |
| 23 | 備考 | — | |

**注意事項**
- URL列（列19）にメールアドレスや電話番号が混入しているケースあり。`http://` または `https://` で始まるもののみ有効とする。
- 法人名（列14）に誤字が含まれる場合がある（例: 「ハローサポー卜」の「卜」は片仮名ではなく漢数字「卜」）。正規化せず生値を `raw_corporation_name` に保持する。
- 定員 `0` は「未記入」として `null` に変換する（居宅介護支援は実質定員制限なし）。

### 2.2 補助データソース（将来対応）

**介護サービス情報公表システム（情報公表詳細ページ）**
- 取得可能な追加情報: ケアマネジャー人数（主任含む）、従業員総数、利用者総数、サービス提供エリア、運営方針テキスト
- 難易度: **高**（SPA/React製のため、Playwright等のブラウザ自動化が必要）
- レート制限・セッション管理あり
- 実装目安: **Phase 3以降**

**都道府県別オープンデータ**
- 大阪府・北海道等が独自のオープンデータを提供している場合がある
- 厚労省データとの差分確認・補完に活用可能
- 都道府県ごとに仕様が異なるため個別対応が必要

### 2.3 後回しデータソース

**Google Places API**
- 口コミ評価（rating）、レビュー件数、写真、営業状態の補完
- 課金が発生するため、大量実行前にコスト試算が必要（100件超で要確認）
- 実装目安: **Phase 2以降**

**WAM-NET**
- 社会福祉施設等情報（WAMNET）は一括取得不可
- 個別ページアクセスが必要で、スケール困難

---

## 3. 共通データ構造

### 3.1 ポータル共通コア（OfficeMaster）

| フィールド名 | 型 | 必須 | 説明 | 訪問看護での対応 | 訪問診療での対応 |
|---|---|---|---|---|---|
| office_id | str | ○ | 一意識別子 | station_id | kikan_cd ベース |
| portal_type | str | ○ | ポータル種別 | (なし) | (なし) |
| service_code | str | ○ | 厚労省コード | "130" | — |
| service_name | str | ○ | サービス名 | "訪問看護" | "訪問診療" |
| name | str | ○ | 事業所名 | name | name |
| name_kana | str | — | カナ | name_kana | (なし) |
| prefecture | str | ○ | 都道府県 | prefecture | pref |
| pref_code | str | ○ | 都道府県コード | (なし) | pref_code |
| city | str | ○ | 市区町村 | city | (address から分割) |
| city_code | str | — | 市区町村コード | (なし) | (なし) |
| address | str | ○ | 住所全文 | address | address |
| address_building | str | — | 方書・ビル名 | (なし) | (なし) |
| postal_code | str | — | 郵便番号 | postal_code | postal |
| tel | str | — | 電話番号 | tel | tel |
| fax | str | — | FAX | fax | (なし) |
| corporation_number | str | — | 法人番号13桁 | (なし) | (なし) |
| corporation_name | str | — | 法人名称 | corporation_name | (なし) |
| office_code | str | ○ | 事業所番号10桁 | office_code | kikan_cd |
| latitude | float | — | 緯度 | latitude | lat |
| longitude | float | — | 経度 | longitude | lng |
| website_url | str | — | 公式URL | website_url | url |
| source_primary | str | ○ | 主ソース名 | source_primary | (固定値) |
| source_url | str | — | データ取得元URL | source_url | (なし) |
| source_updated_at | str | — | ソース更新日 | source_updated_at | (なし) |
| retrieved_at | str | — | 取得処理日時 | (なし) | (なし) |
| is_active | bool | ○ | 稼働中フラグ | is_active | (なし) |
| raw_address | str | — | 正規化前住所 | raw_address | (なし) |
| raw_name | str | — | 正規化前名称 | raw_name | (なし) |
| raw_corporation_name | str | — | 正規化前法人名 | raw_corporation_name | (なし) |

### 3.2 訪問看護との互換性

**フィールド名の汎化提案**

現在の訪問看護 `StationMaster` では `station_id` を使用しているが、
全ポータル共通の識別子として `office_id` に統一することを推奨する。

```
StationMaster.station_id  →  OfficeMaster.office_id  （名称の汎化）
```

それ以外のフィールドは名称・型ともに互換性を保つ。
訪問看護側も将来的に `office_id` への移行を検討すること。

**追加フィールド（居宅介護支援で新規追加）**
- `pref_code`: 都道府県コード2桁（訪問看護にはないが有用）
- `city_code`: 市区町村コード6桁（URL生成・検索に使用）
- `address_building`: 方書（訪問看護にはない）
- `corporation_number`: 法人番号13桁（法人単位の関連付けに必要）
- `portal_type`, `service_code`, `service_name`: ポータル種別メタデータ
- `retrieved_at`: 処理日時（データ鮮度の追跡用）

### 3.3 訪問診療との互換性

| 訪問診療フィールド | → | 共通フィールド | 変換 |
|---|---|---|---|
| kikan_cd | → | office_code | そのまま |
| pref | → | prefecture | そのまま |
| pref_code | → | pref_code | そのまま |
| address | → | address | そのまま |
| lat | → | latitude | そのまま |
| lng | → | longitude | そのまま |
| url | → | website_url | そのまま |

---

## 4. 居宅介護支援固有の拡張（KyotakuFeatures）

| フィールド名 | 型 | CSV列 | 説明 |
|---|---|---|---|
| office_id | str | — | OfficeMaster.office_id と対応 |
| business_days_text | str | 16 | 利用可能曜日（例: 平日、月〜土） |
| business_days_note | str | 17 | 曜日の特記事項 |
| capacity | int | 18 | 定員（0→null変換） |
| inclusive_service | bool | 20 | 共生型サービス対応 |
| meets_kaigo_standard | bool | 21 | 介護保険基準充足 |
| meets_shogai_standard | bool | 22 | 障害福祉基準充足 |
| remarks_raw | str | 23 | 備考（生テキスト） |
| source | str | — | データソース名（固定: "mhlw_opendata"） |

**Phase 3 以降で追加予定（介護サービス情報公表システムより）**
```
care_manager_count         # ケアマネジャー人数
chief_care_manager_count   # 主任ケアマネジャー人数
employee_total             # 従業員総数
users_total                # 利用者総数
service_area_text          # サービス提供エリア（テキスト）
operating_policy_text      # 運営方針テキスト
```

---

## 5. CSVカラム → スキーマ マッピング表

| CSV列名 | CSV列番号 | → | スキーマフィールド | 変換処理 |
|---|---|---|---|---|
| 都道府県コード又は市町村コード | 0 | → | city_code | そのまま（6桁文字列） |
| No | 1 | → | office_code | そのまま（事業所番号と同値） |
| 都道府県名 | 2 | → | prefecture | そのまま |
| 市区町村名 | 3 | → | city | そのまま |
| 事業所名 | 4 | → | name, raw_name | raw_name に生値保存、name に正規化後保存 |
| 事業所名カナ | 5 | → | name_kana | NFKC正規化 |
| サービスの種類 | 6 | → | service_name | 確認用（固定値「居宅介護支援」） |
| 住所 | 7 | → | address, raw_address | raw_address に生値保存、address に正規化後保存 |
| 方書（ビル名等） | 8 | → | address_building | 空欄→null |
| 緯度 | 9 | → | latitude | float変換 |
| 経度 | 10 | → | longitude | float変換 |
| 電話番号 | 11 | → | tel | そのまま（既にハイフン付き） |
| FAX番号 | 12 | → | fax | そのまま |
| 法人番号 | 13 | → | corporation_number | 文字列で保持（13桁） |
| 法人の名称 | 14 | → | corporation_name, raw_corporation_name | raw に生値保存 |
| 事業所番号 | 15 | → | office_code | 主キー |
| 利用可能曜日 | 16 | → | business_days_text | KyotakuFeatures |
| 利用可能曜日特記事項 | 17 | → | business_days_note | KyotakuFeatures |
| 定員 | 18 | → | capacity | int変換、0→null |
| URL | 19 | → | website_url | http/httpsのみ有効。他は null |
| 共生型サービス | 20 | → | inclusive_service | 有→true、無→null |
| 介護保険基準充足 | 21 | → | meets_kaigo_standard | 同上 |
| 障害福祉基準充足 | 22 | → | meets_shogai_standard | 同上 |
| 備考 | 23 | → | remarks_raw | そのまま、空欄→null |

**office_id の生成ルール**
```
office_id = "kyotaku-" + office_code
例: "kyotaku-0170102313"
```

**pref_code の導出**
```
city_code の先頭2桁
例: city_code="011011" → pref_code="01"
```

---

## 6. データ統合戦略

### 主キー
- `office_code`（事業所番号10桁）を主キーとして使用
- CSVの列1（No）と列15（事業所番号）は同値

### マージキー優先順位（複数ソース統合時）

| 優先順 | マージキー | 精度 |
|---|---|---|
| 1 | office_code 完全一致 | 高 |
| 2 | normalized_name + normalized_address | 中 |
| 3 | name + tel | 中 |
| 4 | fuzzy → review_candidates | 低（手動確認） |

### 法人単位の関連付け
- `corporation_number`（法人番号13桁）を使って、同一法人の複数事業所を紐付けられる
- 将来的には訪問看護・訪問診療との**クロスポータル関連**も可能
  - 例: 同一法人が訪問診療・訪問看護・居宅介護支援を運営している場合、法人番号で紐付け

### 重複排除ルール
- 厚労省CSV単体では事業所番号が重複しないはずだが、処理後に確認すること
- 複数ソース統合後は上記マージキーで重複チェック

---

## 7. 正規化ルール

| 対象 | ルール |
|---|---|
| 全角英数字 | NFKC正規化（全角→半角）: `unicodedata.normalize('NFKC', text)` |
| 電話番号 | ハイフン付き形式 NNN-NNNN-NNNN を維持（CSVは既にこの形式） |
| FAX番号 | 同上 |
| 郵便番号 | NNN-NNNN（CSVには含まれないため将来補完時に適用） |
| 住所 | 都道府県含む全文を `address` に保持。方書は `address_building` に分離 |
| 法人名 | 原文保持（「株式会社→(株)」等の変換はしない）。誤字も raw に保存 |
| URL | http/https で始まるもののみ有効。メールアドレス等は null に変換 |
| 定員 | 0 → null（居宅介護支援は実質定員制限なし） |
| 空文字列 | "" → null（全フィールド共通） |
| 緯度経度 | float変換。精度は小数点以下7桁程度に丸め可 |

---

## 8. 静的サイト生成のデータレイヤ

### raw層（取得そのまま）
```
data_sources/mhlw/raw_jigyosho_430.csv    ← ダウンロードしたCSV（変更しない）
```

### normalized層（正規化済み）
```
data_sources/processed/mhlw_normalized.csv    ← 正規化スクリプトの出力
```

### build層（サイト生成用）
```
data/offices_kyotaku.json        ← 全件・正規化済み（メインデータ）
data/search/{pref_code}.json     ← 都道府県別検索用（01.json〜47.json）
data/offices_geo.json            ← 地図用軽量版（office_id, lat, lng, name のみ）
```

### ページ生成
```
dist/index.html                              ← 全国トップページ
dist/pref/{slug}.html                        ← 都道府県一覧（例: hokkaido.html）
dist/pref/{slug}/{city_slug}.html            ← 市区町村一覧
dist/office/{office_code}.html              ← 個別詳細ページ
```

**想定ページ数**
- 都道府県ページ: 47件
- 市区町村ページ: 約1,800件
- 個別詳細ページ: 36,491件
- 合計: **約38,338ページ**

---

## 9. MVP項目整理

### Phase 1 — 必須（厚労省CSV 1本で完結）
厚労省CSVから以下のフィールドを取得できる。この範囲でMVPを完成させる。

```
office_id, name, name_kana, prefecture, pref_code, city, city_code,
address, address_building, tel, fax, corporation_number, corporation_name,
office_code, latitude, longitude, website_url,
source_primary, is_active,
business_days_text, capacity
```

**実装内容**
1. CSV取得（download_csv.py）
2. 正規化・JSON変換（normalize.py）
3. 静的サイト生成（build_site.py）
4. デプロイ

### Phase 2 — 追加候補（優先度: 中）
```
business_days_note, inclusive_service, meets_kaigo_standard, meets_shogai_standard
Google Places連携: rating, review_count, photo_url, business_status
```

### Phase 3 — 後回し（情報公表システムスクレイピング必要）
```
care_manager_count, chief_care_manager_count, employee_total,
users_total, service_area_text, operating_policy_text
```

---

## 10. 実装順序

| ステップ | 内容 | 目安工数 |
|---|---|---|
| Step 1 | CSV取得 → 正規化 → JSON出力（normalize.py実装） | 0.5日 |
| Step 2 | 静的サイト生成（build_site.py移植・訪問看護から流用） | 2〜3日 |
| Step 3 | デプロイ・ドメイン設定 | 0.5日 |
| Step 4 | Google Places連携 | 後日 |
| Step 5 | 介護サービス情報公表システムスクレイピング | Phase 3 |

---

## 11. ライセンス・注意事項

**CC BY 4.0 について**
- 出典明記のうえ商用利用可（広告収益・有料プラン等を含む）
- 出典表記: `介護サービス情報公表システム（厚生労働省）のデータを基に作成`
- データの加工・再配布も可能

**個人情報の取り扱い**
- 厚労省CSV に含まれる情報は事業所の公開情報（個人名は含まれない）
- 居宅介護支援事業所の電話番号・住所はすでに公開されている情報
- 担当ケアマネジャーの個人名は表示しない（CSVには含まれないが、将来スクレイピング時に注意）

**データ鮮度**
- 厚労省CSVは年2回更新（6月末・12月末）
- 更新後は必ず再ダウンロード → 再ビルド → 再デプロイのフローを踏む
- `source_updated_at` フィールドで鮮度を管理する

---

## 付録A: フィールド対応表（3ポータル横断）

| 共通フィールド名 | 居宅介護支援 (kyotaku-navi) | 訪問看護 (houmonkango-navi) | 訪問診療 (zaitaku-clinic-navi) |
|---|---|---|---|
| office_id | office_id | station_id | kikan_cd ベース |
| name | name (CSV列4) | name | name |
| name_kana | name_kana (CSV列5) | name_kana | (なし) |
| prefecture | prefecture (CSV列2) | prefecture | pref |
| pref_code | city_code先頭2桁 | (なし) | pref_code |
| city | city (CSV列3) | city | (address分割) |
| address | address (CSV列7) | address | address |
| tel | tel (CSV列11) | tel | tel |
| fax | fax (CSV列12) | fax | (なし) |
| corporation_name | corporation_name (CSV列14) | corporation_name | (なし) |
| corporation_number | corporation_number (CSV列13) | (なし) | (なし) |
| office_code | office_code (CSV列15) | office_code | kikan_cd |
| latitude | latitude (CSV列9) | latitude | lat |
| longitude | longitude (CSV列10) | longitude | lng |
| website_url | website_url (CSV列19) | website_url | url |
| is_active | is_active | is_active | (なし) |
| rating | OfficeWeb.rating | StationWeb.rating | rating |
| review_count | OfficeWeb.review_count | StationWeb.review_count | review_count |
| photo_url | OfficeWeb.photo_url | StationWeb.photo_url | photo_url |

---

## 付録B: データ品質チェックポイント

ビルド・デプロイ前に必ず確認する項目：

```
全国件数: 36,491件 ± 100件の範囲内か
都道府県数: 47都道府県すべて存在するか
北海道件数: 2,000件前後か（CSVの件数比で推算）
東京都件数: 3,000件前後か
神奈川県件数: 1,500件前後か
緯度経度の欠損: 0件であること（100%充填のため）
重複office_code: 0件であること
```

異常があればビルドを停止し、原因を特定してから再実行する。
