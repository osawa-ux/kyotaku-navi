# 代理指標フィルタ有効化手順

## 現在の状態

`config/site_config.json` の `differentiator_filters.build_enabled` が `false` のため、
フィルタUI（都道府県・市区町村ページのチェックボックス）と事業所バッジは非表示です。

これは Reviewer C1/C2 対応として実施した変更です:
- **C1**: null データで「準備中」UI が本番全ページに表示されると品質シグナルが低下する → データ取得まで非表示
- **C2**: `dist/feature/kanagawa-terminal_care_addon.html`（null データのデモ 20 件）が dist/ に混入 → `dist/_demo/` に隔離

## 有効化の前提条件

以下の 4 フィールドに実データが充填されていること:

| フィールド | 意味 | 型 |
|---|---|---|
| `terminal_care_addon` | ターミナルケアマネジメント加算の算定実績 | bool または null |
| `specific_office_addon` | 特定事業所加算（I/II/III/A）の算定 | bool または null |
| `emergency_phone_support` | 緊急時の電話連絡対応 | bool または null |
| `chief_caremanager_count` | 主任介護支援専門員の在籍数 | int または null |

データソース: 介護サービス情報公表システム（kaigokensaku）詳細スクレイピング

## 有効化手順

```bash
# 1. kaigokensaku データ取得・正規化（スクリプトは将来実装）
python scripts/normalize.py --include-kensaku-details

# 2. site_config.json の build_enabled を true に変更
#    config/site_config.json の "build_enabled": false を "build_enabled": true に書き換える

# 3. リビルド（Pre-Build Validation: 38,403 件維持を確認）
python build_site.py

# 4. 件数確認
grep -c 'class="card caremanager-card"' dist/pref/kanagawa.html

# 5. フィルタ UI が表示されていることを確認
grep -c 'diff-filters' dist/pref/kanagawa.html
# → 1 以上であれば OK

# 6. 確認後にデプロイ
```

## デモファイルの取り扱い

`dist/_demo/feature/` 配下はデモ用（null データを強制 True にしたサンプル）です。
本番デプロイ時は gh-pages 同期スクリプトから `_demo/` を除外してください。

```bash
# gh-pages 同期時の除外例
rsync -av --exclude='_demo/' dist/ /tmp/kyotaku-gh-pages/
```

## フィーチャーページ量産（Phase 2）

フィルタ有効化後、全都道府県 × 4 フィルタのフィーチャーページを生成できます:

```bash
python scripts/build_feature_pages.py --phase 2
# → dist/feature/{pref}-{filter}.html を最大 188 ページ生成（データのある組み合わせのみ）
```
