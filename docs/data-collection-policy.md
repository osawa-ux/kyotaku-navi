# データ収集ポリシー — kaigokensaku.mhlw.go.jp

最終更新: 2026-05-13

## 1. 対象データソース

- **サイト名**: 介護サービス情報公表システム
- **URL**: https://www.kaigokensaku.mhlw.go.jp/
- **運営**: 厚生労働省
- **利用規約**: https://www.kaigokensaku.mhlw.go.jp/copyright/
- **オープンデータ CSV**: CC BY 4.0 ライセンス（https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html）

## 2. スクレイピング対象と方針

### 対象

`scripts/download_kaigokensaku.py` は、CC BY 4.0 の公開 CSV（`jigyosho_430.csv`）では
取得できない以下の 4 属性を詳細ページから補完取得する:

- ターミナルケアマネジメント加算 有無 (`terminal_care_addon`)
- 特定事業所加算 有無 (`specific_office_addon`)
- 緊急時電話連絡対応 有無 (`emergency_phone_support`)
- 主任介護支援専門員数 (`chief_caremanager_count`)

### robots.txt 確認結果（2026-05-12 時点）

```
User-agent: *
Disallow: /shuukei
Disallow: /kanri
Disallow: /houkoku
Disallow: /seikatu_kanri
Disallow: /err
Disallow: /upload
```

事業所詳細ページ (`/NN/index.php?action_kouhyou_detail_*`) は Disallow 対象外。

### rate limit 設計

- 1リクエスト / 2〜3秒（ランダム）
- 10件ごとに5秒の追加休止
- 識別可能な Contact ヘッダー（`X-Contact`）を付与

## 3. 法的リスク評価

### リスクが低いと判断する根拠

1. **公的データ**: 厚生労働省が国民向けに公表している情報であり、情報そのものは公開済み
2. **同一目的**: サイトの公表目的（利用者への介護事業所情報提供）と care.zaitaku-navi.com の
   提供目的（患者・家族・医療関係者のケアマネ選択支援）が合致する
3. **出所表示**: CC BY 4.0 の要求する出所表示を全ページフッターに実装済み
4. **負荷配慮**: rate limit を設け、サイト運営への影響を最小化

### 残存リスク（要注意）

**利用規約「関係のない営利行為等の対象にする行為は禁止」との整合性:**

- care.zaitaku-navi.com は有料プラン（月¥55,000〜¥110,000）を持つ商業サービス
- 「営利行為」に該当するかどうかは規約の解釈次第であり、法的保証はできない
- **判断責任は運営者（osawa / MDX株式会社）が負う**

**推奨対応:**

- フリープラン（¥0）のみの段階ではリスクは相対的に低い
- 有料プランの本格展開前に法律専門家に確認することを強く推奨
- 問い合わせがあった場合は「対処手順（第5節）」に従い即時対応する

## 4. 出所表示の実装

`build_site.py` の `make_footer()` に以下の HTML を実装済み:

```html
<p class="data-source">
  データ出典:
  <a href="https://www.kaigokensaku.mhlw.go.jp/" target="_blank" rel="noopener">
    介護サービス情報公表システム
  </a>
  （厚生労働省、<a href="https://creativecommons.org/licenses/by/4.0/deed.ja" target="_blank" rel="noopener">CC BY 4.0</a>）
</p>
```

全ページのフッターに表示される。詳細ページの「データ出典」セクションにも同様の表示あり。

## 5. 問い合わせ・指摘があった場合の対処手順

1. **即時停止**: 全件実行を停止する（`Ctrl+C` またはプロセスキル）
2. **データ非公開**: 問題の指摘を受けたデータを含むページをサイトから削除またはnoindex化
3. **連絡対応**: 24時間以内に誠実に返信する。連絡先: osawa@yokohama-home.jp
4. **判断**: 指摘内容を確認し、問題があれば該当スクリプトを廃止する
5. **記録**: 対応内容を本ドキュメントに追記する

## 6. 環境変数設定（I1 対応）

スクリプトはリクエスト時の `X-Contact` ヘッダーを環境変数から読み込む:

```bash
# .env.local に追記（.gitignore 対象、コミットしない）
KAIGOKENSAKU_CONTACT=your-email@example.com (zaitaku-navi public data collection)
```

設定しない場合はデフォルト値 `care-data-collection/1.0 (please set KAIGOKENSAKU_CONTACT env var)` が使用される。

実行前に以下で環境変数を読み込む（bash の場合）:

```bash
set -a && . .env.local && set +a
python scripts/download_kaigokensaku.py --dry-run
```

PowerShell の場合:

```powershell
Get-Content .env.local | ForEach-Object {
    if ($_ -match '^([^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
    }
}
python scripts/download_kaigokensaku.py --dry-run
```

## 7. 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-05-13 | 初版作成（Reviewer C1 対応） |
