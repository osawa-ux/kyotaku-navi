# 居宅介護支援ナビ (kyotaku-navi)

全国の居宅介護支援事業所（ケアマネジャー事業所）を検索できる静的ポータルサイト。

- **公開予定URL**: https://care.zaitaku-navi.com
- **親ドメイン**: `zaitaku-navi.com`（`clinic.` / `kango.` / `care.` / `shika.` / `welfare.` を並列展開予定）
- **データソース**: 厚生労働省 介護サービス情報公表システム オープンデータ (CC BY 4.0)
- **掲載件数**: 36,491件（全47都道府県、2025年時点）
- **ステータス**: ビルド完成・デプロイ手前まで完了

## 現在の進捗

### ✅ 完了
- [x] データ構造設計 (`docs/kyotaku-care-support-data-design.md`)
- [x] Pydanticスキーマ (`models/office_schema.py`) — OfficeMaster / KyotakuFeatures / OfficeWeb / ScrapeAudit
- [x] CSVダウンロード (`scripts/download_csv.py`)
- [x] 正規化 (`scripts/normalize.py`) — 36,491件、全10項目品質チェック通過
- [x] 静的サイト生成 (`build_site.py`) — 38,400ページ生成
- [x] 一気通しパイプライン (`scripts/run_pipeline.py`)
- [x] ドメイン設定 `care.zaitaku-navi.com`
- [x] CNAMEファイル生成
- [x] `/caremanager/` カテゴリ別URL構造（将来 home-help / day-service 等を並列展開可能）
- [x] パンくずにカテゴリ階層追加
- [x] トップページにカテゴリ選択UI追加

### 🟡 進行中（次回再開ポイント）
- [ ] **Cloudflare DNS に `CNAME care → osawa-ux.github.io` 追加** ← 次はここから
- [ ] `gh-pages` ブランチ作成・`dist/` を push
- [ ] GitHub Pages 有効化・カスタムドメイン設定
- [ ] HTTPS 強制有効化
- [ ] 動作確認 (`curl -I https://care.zaitaku-navi.com/`)

### 🔵 公開後対応
- [ ] GA4 計測ID設定・再ビルド
- [ ] Search Console 登録・sitemap 送信
- [ ] 定期ビルド自動化（年2回のCSV更新対応、GitHub Actions cron）

## ディレクトリ構成

```
kyotaku-navi/
├── build_site.py                  # 静的サイト生成メインスクリプト
├── config/
│   ├── site_config.json           # サイト設定（URL, カテゴリ, GA4 等）
│   ├── schema.yaml                # フィールド定義
│   └── sources.yaml               # データソース定義
├── models/
│   └── office_schema.py           # Pydanticスキーマ
├── scripts/
│   ├── download_csv.py            # 厚労省CSVダウンロード
│   ├── normalize.py               # CSV → 正規化JSON
│   └── run_pipeline.py            # 一気通しパイプライン
├── docs/
│   ├── kyotaku-care-support-data-design.md  # 設計ドキュメント
│   ├── data-sources-research.md             # データソース調査
│   └── schemas/
│       └── kyotaku_care_support_example.json
├── data/                          # ← .gitignore（ビルド時生成）
│   ├── raw/jigyosho_430.csv
│   └── normalized/
│       ├── offices_430.json
│       └── offices_430.jsonl
└── dist/                          # ← .gitignore（ビルド出力）
    ├── index.html
    ├── CNAME
    ├── caremanager/
    │   ├── index.html                            # カテゴリトップ
    │   └── mhlw_kaigo_{code}_430.html           # 詳細（36,491枚）
    ├── pref/
    │   ├── {slug}.html                           # 都道府県（47枚）
    │   └── {slug}/{city}.html                    # 市区町村（1,861枚）
    ├── data/
    │   ├── search/{pref_code}.json               # 都道府県別検索JSON
    │   ├── offices_geo.json                      # 地図用軽量JSON
    │   └── stats.json
    ├── sitemap.xml                               # 38,201 URL
    ├── robots.txt
    └── static/
        ├── style.css
        └── search.js
```

## 使い方

### フルビルド（推奨）
```bash
python scripts/run_pipeline.py --clean
```
download → normalize → build を一気通しで実行。約30〜60秒。

### ビルドのみ（CSVと正規化JSON既存の場合）
```bash
python scripts/run_pipeline.py --from build --clean
```
約20秒。

### ローカルプレビュー
```bash
python scripts/run_pipeline.py --from build --preview
# http://localhost:8000/
```

### その他のオプション
```bash
python scripts/run_pipeline.py --skip-download    # ダウンロード省略
python scripts/run_pipeline.py --from normalize   # 正規化から開始
python scripts/run_pipeline.py --verbose          # 詳細ログ
```

## データフロー

```
厚労省CSV (jigyosho_430.csv)
  ↓ scripts/download_csv.py
data_sources/mhlw/raw_jigyosho_430.csv
  ↓ run_pipeline.py がコピー
data/raw/jigyosho_430.csv
  ↓ scripts/normalize.py (NFKC, 電話バリデーション, URL検証)
data/normalized/offices_430.json (+ .jsonl)
  ↓ build_site.py
dist/ (静的HTML + JSON + sitemap)
```

## アーキテクチャのポイント

### 1. サービスカテゴリ構造
`site_config.json` の `service_categories` 辞書を拡張するだけで、同一ドメイン内に `/caremanager/`, `/home-help/`, `/day-service/` 等を並列展開できる。

```json
"service_categories": {
  "caremanager": {
    "label": "ケアマネジャー事業所",
    "url_prefix": "caremanager",
    "service_code": "430"
  }
}
```

各レコードは `service_category` フィールドを持ち、`detail_url(o)` が `/{category}/{slug}.html` を動的生成する。build_site.py はカテゴリ別ディレクトリを自動作成。

### 2. 共通コア + 業種拡張スキーマ
`OfficeMaster`（全ポータル共通）+ `KyotakuFeatures`（居宅介護支援固有）の2層構造。訪問看護ナビ・訪問診療ナビと将来 `shared/` 化可能な設計。

### 3. 都道府県別検索JSON分割
`data/search/{pref_code}.json` で初期ロードを軽量化。フルテキストは `st` フィールドに結合済み。

## ドメイン戦略

`zaitaku-navi.com` を親ドメインとし、サブドメインで並列展開：

| サブドメイン | ポータル | リポジトリ | ステータス |
|------------|---------|----------|----------|
| `clinic.zaitaku-navi.com` | 訪問診療ナビ | `MyPython/` | 移行予定（現: `zaitakuclinic-navi.com` 稼働中） |
| `kango.zaitaku-navi.com` | 訪問看護ナビ | `houmonkango-navi/` | DNS設定済（サイト未公開） |
| **`care.zaitaku-navi.com`** | **居宅介護支援ナビ** | **`kyotaku-navi/`** | **本リポジトリ、公開手前** |
| `shika.zaitaku-navi.com` | 訪問歯科ナビ | 未作成 | 将来 |
| `welfare.zaitaku-navi.com` | 障害福祉ナビ | 未作成 | 将来 |

## デプロイ手順（次回再開時）

### 前提
- Cloudflare: `zaitaku-navi.com` ゾーン `d2ee309f0a2fb373a09f0deb6669d7a2` (active)
- Cloudflare API トークン: `~/.secrets/cloudflare/.env` の `CF_API_TOKEN`
- GitHub認証: `gh` CLI ログイン済み (osawa-ux, scopes: `repo`)

### ステップ 1: Cloudflare DNS 追加
```bash
set -a && . ~/.secrets/cloudflare/.env && set +a
ZONE_ID="d2ee309f0a2fb373a09f0deb6669d7a2"  # zaitaku-navi.com
curl -s -X POST \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"type":"CNAME","name":"care","content":"osawa-ux.github.io","proxied":false,"ttl":1,"comment":"kyotaku-navi GitHub Pages"}' \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records"
```

### ステップ 2: `gh-pages` ブランチを作成して dist/ を push
```bash
cd ~/projects/kyotaku-navi
python scripts/run_pipeline.py --clean  # 最新ビルド

# 別ディレクトリで初期化（master に影響を与えないため）
cp -r dist /tmp/kyotaku-gh-pages
cd /tmp/kyotaku-gh-pages
git init -b gh-pages
git add -A
git commit -m "Deploy care.zaitaku-navi.com"
git remote add origin https://github.com/osawa-ux/kyotaku-navi.git
git push -f origin gh-pages
```

### ステップ 3: GitHub Pages 有効化 + カスタムドメイン
```bash
gh api -X POST repos/osawa-ux/kyotaku-navi/pages \
  -f "source[branch]=gh-pages" \
  -f "source[path]=/"

gh api -X PUT repos/osawa-ux/kyotaku-navi/pages \
  -f "cname=care.zaitaku-navi.com"
```

### ステップ 4: HTTPS 強制（DNS check 完了後）
```bash
gh api -X PUT repos/osawa-ux/kyotaku-navi/pages \
  -F "https_enforced=true"
```

### ステップ 5: 動作確認
```bash
curl -I https://care.zaitaku-navi.com/
curl -s https://care.zaitaku-navi.com/sitemap.xml | head -5
curl -s https://care.zaitaku-navi.com/caremanager/ | grep -o '<title>.*</title>'
```

## 検証結果（最終ビルド）

```
=== 居宅介護支援ナビ パイプライン (27.2秒) ===

データ件数:    36,491
都道府県ページ:     47
市区町村ページ:  1,861
詳細ページ:     36,491 (dist/caremanager/)
カテゴリトップ:      1 (dist/caremanager/index.html)
検索JSON:       47ファイル
sitemap URL:  38,201

全10項目検証 通過
```

## ライセンス・出典

- **データ出典**: 介護サービス情報公表システム（厚生労働省）のデータを基に作成
- **データライセンス**: CC BY 4.0
- **運営者**: MDX株式会社
