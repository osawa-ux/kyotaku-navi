---
status: accepted
date: 2026-07-05
decision-makers: 院長
---
# 0000: ADR を連番 MADR で記録する

## Context and Problem Statement

kyotaku-navi の意思決定（構造・非機能・依存・外部 IF・データモデル・規制対応方針）が
チャットや記憶に散逸すると、後から「なぜこの選択をしたか」を追跡できなくなる。
architecturally significant な決定を記録する標準形式・置き場所が必要。

## Considered Options
- 自由形式の Markdown メモを `docs/design/` に随時追加する
- 連番 MADR（Markdown Architectural Decision Records）を `docs/decisions/` に記録する

## Decision Outcome

選択: 連番 MADR。`docs/decisions/NNNN-主題.md`（4 桁連番・再利用禁止）で記録する。
理由: 監査可能性（いつ何を決めたか）と不変性（決定履歴の改ざん防止）を両立できる。

### 運用ルール（要約）

1. **いつ書くか**: architecturally significant な決定のみ（構造・非機能・依存・外部 IF・データモデル・規制対応方針）。日々の実装判断は書かない
2. **不変性**: 既存 ADR は書き換えない。変更は新 ADR＋旧 ADR の `status` を `superseded by NNNN` に更新
3. **番号**: 4 桁連番・再利用禁止
4. **regulated 決定の人間ゲート**: 算定・PHI・法務に関わる ADR は `decision-makers` に院長を記録し、accepted 遷移は人間承認後のみ
5. **CLAUDE.md との接続**: CLAUDE.md には「決定の正本は `docs/decisions/`」の 1 行のみ記載。ADR 全文を import しない
6. **subagent 委譲との接続**: 実装 brief には関連 ADR / design doc のパスを入力として明示し、レビュー subagent には diff を ADR/design と突き合わせるよう指示する

### Consequences
- Good: 意思決定が監査可能になり、後任・他 agent が経緯を追跡できる
- Bad: 決定のたびに 1 ファイル増える運用コストが発生する（過剰記録を避けるため上記 1. で発火条件を絞る）

## Confirmation

新規 ADR 追加時に `docs/decisions/` の連番が重複していないか・regulated 決定の
`status` 遷移が人間承認を経ているかをレビュー時に確認する。

運用正本: vault `70_SOP/product-docs-adr.md`
