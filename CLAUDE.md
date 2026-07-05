# CLAUDE.md — kyotaku-navi

居宅介護支援ポータル（ケアマネジャー事業所検索、厚労省 介護サービス情報公表システム オープンデータ基盤）

- repo: `kyotaku-navi`
- project: `care`
- domain: `care.zaitaku-navi.com`
- sister sites: clinic, kango, shika, welfare

---

## 上位原則

本repoは Obsidian の `30_Areas/開発運用原則.md` を上位原則として参照する。
repo固有ルールはこの CLAUDE.md に限定し、原則全文は複製しない。

共通ルール・保存判断基準・出力フォーマットは `~/.claude/CLAUDE.md`（グローバル）および Obsidian vault 内の関連ノートを参照。

---

## Obsidian 連携の最小ルール

vault 同期は Obsidian Sync 管理（Git / push-pc / sync-pcs は vault 本体の同期には使わない）。

vault path は動的解決:

```bash
python ~/.claude/skills/_shared/resolve_vault.py                            # vault root
python ~/.claude/skills/_shared/resolve_vault.py --join "10_Daily/..."      # 子パス
```

→ 絶対パスを CLAUDE.md に直接書かない。別PC・vault 移動にも追従できる。

### いつ Obsidian を読むか

- 軽微な修正（typo、文言、フォーマット、単発バグ修正）では **不要**
- 影響範囲が大きいタスクでは、実装前に relevant notes を確認する
- 特に以下では読むことを **優先する**:
  - 共通基盤・横断設計に関わる変更
  - SEO 方針・内部リンク設計
  - データ構造・スキーマの変更
  - 過去の重要判断を踏まえる必要がある変更
  - 久しぶりに再開するタスク

### 読む候補ノート（Vault 内の相対パス）

現行 vault 体系（`00_Inbox` / `10_Daily` / `20_Projects` / `30_Areas` / `40_Resources` / `50_Research` / `60_Decisions` / `60_Meetings` / `70_SOP` / `80_Templates` / `85_Prompts` / `90_Templates` / `99_Archive`）から、この repo で参照頻度が高いもの:

- `20_Projects/care/index.md` — この repo の現在地・重要論点
- `30_Areas/` — 領域・継続テーマ（開発運用原則 等）
- `40_Resources/` — 共通リソース・参照資料
- `60_Decisions/` 配下の意思決定ログ
- `70_SOP/` 配下の標準業務手順書（算定 / チャット返信 / SEO 等のドメイン判断時）
- 必要なら当日の `10_Daily/YYYY-MM-DD.md`

### Vault の特定（PC非依存）

Vault の絶対パスはこのテンプレには埋め込まない（PC ごとに異なるため）。運用方針の正本は Vault 内の `_Vault運用方針.md`。

PC 別の Vault path は resolver で解決する（絶対パス直書き禁止）:
```bash
python ~/.claude/skills/_shared/resolve_vault.py
```
解決順: `$OBSIDIAN_VAULT` → Obsidian アプリ設定（`%APPDATA%\obsidian\obsidian.json` の open=true な vault）→ `~/Obsidian`

---

## 能力カタログ連携

source of truth は Obsidian `30_Areas/能力カタログ.md`（索引兼台帳）。
詳細は `30_Areas/capabilities/<domain>/<能力ID>.md`、共通方針は `30_Areas/capability-guides/`。

### この repo での更新義務

- **新しい再利用可能能力を実装したら** `30_Areas/能力カタログ.md` の該当セクションに追記する
- **既存能力の status / owner / 実装場所 / 概要 / 廃止判断が変わったら** catalog を更新する
- 大きい能力（運用ルール・制約・履歴が増えるもの）は `30_Areas/capabilities/<domain>/<能力ID>.md` に詳細ページを作る

### 登録するもの・しないもの

- 登録するもの: **横断再利用価値があるもの**（他 repo / 他 agent から呼び出される or 呼び出され得る能力）
- 登録しないもの: repo 内部で閉じた小関数、単発の探索スクリプト、調査用のワンショットコード
- 粒度は「**1動詞 1目的語**」寄り
  - ✗ 「Foo 対応済み」 ✓ 「Foo にログインできる」「当日の Foo 一覧を取得できる」

### 登録時の最小情報

`能力ID / 能力名 / 状態 / 実行レベル / owner / 最終確認 / 詳細リンク（任意）`

- 命名規則: `<DOMAIN>-<VERB>-<NN>` 形式（例: `MAIL-SEND-01`, `CF-PROTECT-SETUP-01`）。詳細は `30_Areas/capability-guides/命名規則.md`
- 状態定義: `planned / active_unverified / active / broken / archived`。詳細は `30_Areas/capability-guides/ステータス定義.md`
- 実行レベル: `read_only / draft_only / write_with_confirmation / manual_only`

迷ったら `10_Daily/` に1行残し、日次/月次レビューで昇格可否を判断。

### この repo に該当する能力 ID（既存登録分）

- `KYOTAKU-DOWNLOAD-01`
- `KYOTAKU-NORMALIZE-01`
- `KYOTAKU-BUILD-01`

新規追加・状態変更時は catalog 本体と本セクションの両方を更新する。

---

## Obsidian 保存方針（この repo でも同じ）

詳細はグローバル `~/.claude/CLAUDE.md` の「Obsidian 保存ルール」と memory の
`feedback_obsidian_autosave_policy.md` を参照。本セクションは repo 固有の
補足のみ。

### Daily / Project / SOP の三層運用

| 保存先 | 役割 | この repo での書き方 |
|---|---|---|
| `10_Daily/YYYY-MM-DD.md` | 時系列インデックス | **3〜8 行の短文ログ**。作業 / 判断 / 変更 / 残TODO / 関連。詳細は Project / SOP へリンク |
| `20_Projects/care/index.md` | この repo の現在地 | 状態変化・節目（deploy / push / 仕様変更）・未解決 TODO・関連 commit / docs |
| `70_SOP/` `30_Areas/` | 再利用可能ルール | この repo で確立した手順で他 repo にも展開できるもの |

「迷ったら残す。ただし詳細は最小限。Daily に詳細を蓄積させない」が原則。

### multi-step task 終了時の Obsidian 記録判断

**ユーザーの「成果物」リストに Obsidian が無くても、必ず判断する**（4 択、複数可）:
1. Daily 短文ログ（軽い作業・1 日完結）
2. Project 更新（継続案件の節目）
3. SOP 昇格（再利用可能ルール確立）
4. 記録なし（明確な理由がある場合のみ）

### kyotaku-navi で保存優先度が高いテーマ

以下は「他 repo に横展開できる」「過去判断を後から辿る必要が出る」テーマ。
**長文化したら Daily ではなく `20_Projects/care/index.md` または SOP に
書く**。

1. 介護サービス情報公表システム データソースの正規化・更新判断
2. 居宅介護支援（ケアマネ事業所）のカテゴリURL設計（/caremanager/ 等）
3. clinic/kango/shika/welfare との横断導線
4. 親ハブ zaitaku-navi.com との SEOテンプレ共通化
5. 本番運用観測（GA4 / 件数監査 / HTTPS）

### 保存しないもの（この repo の例）

- 軽微な文言・スタイル・フォーマット修正
- 単発の探索的デバッグ・一時的な作業ログ
- 生ログ / 試行錯誤の全履歴 / 使い捨てコマンド列
- 既に別ノート / Project ログに残してある内容の重複メモ
- センシティブ情報（秘密鍵、トークン、患者情報 等）

ただし、小修正でも上記テーマに波及する知見があれば Daily に短く残してよい。

---

## 作業完了時の報告形式

multi-step task の最後に、**TodoWrite の最終 todo は必ず**:

```
Obsidian 記録判断: Daily短文ログ / Project更新 / SOP昇格 / 記録なし
```

にする。「Daily 追記」とだけ書かない。**保存先の振り分けまで含める**。

**記録した場合の報告（複数該当可）:**

```
- Daily 追記: 10_Daily/YYYY-MM-DD.md / 要約: <1行>
- Project 更新: 20_Projects/care/index.md / 要約: <1行>
- SOP 昇格: 70_SOP/<sop>.md / 要約: <1行>
```

**記録しなかった場合:**

```
- Obsidian 記録なし
- 理由: <なぜ記録しないか>
```

「迷ったら残す」が原則のため、記録なし判断は **理由を明記する**。

---

## MEMORY.md 運用（短いポインタ）

`~/.claude/projects/*/memory/` の運用は user-global。詳細ルールはグローバル `~/.claude/CLAUDE.md` の「MEMORY.md 運用」セクションと、Obsidian `_Vault運用方針.md` の「13. MEMORY.md 運用ルール」参照。

repo 作業時に意識すること:
- **MEMORY = 軽量 index + 短い原則**。詳細手順・テンプレ・事例は Obsidian `70_SOP/` へ置く
- 新規 `feedback_*.md` は 50行以内。超えそうなら SOP 分離
- skill 実行時に読まれるべき挙動ルールは auto-memory でなく vault の `30_Areas/<skill>-patterns/`（委任型 skill レジストリ・正本 `70_SOP/obsidian-save-policy.md`）に書く
