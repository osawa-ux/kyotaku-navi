#!/usr/bin/env python3
"""export_supabase_seed.py — care 施設 → zaitaku-members facilities seed 生成（DB 非接続）

在宅ナビ統合プラットフォーム P1-b 第1イテレーション。
data/normalized/offices_430.json（介護サービス情報公表システム由来・36,491 件）を
zaitaku-members の facilities テーブル形式（service_key='care'）に変換し、
dist/supabase/ 配下に seed（JSONL + SQL）を生成する。

## しないこと（スコープ外・重要）

- ネットワーク／DB 接続を一切しない（純ローカル変換）。
- 本番/ステージング Supabase への投入をしない（生成物はファイルのまま）。
- 入力データ（data/）を変更しない（read-only 入力）。

## 接続先スキーマ（zaitaku-members/supabase/migrations/006_facilities.sql）

  facilities(service_key, external_facility_id, facility_name,
             postal_code, prefecture, city, address_line1, address_line2)
  複合一意: (service_key, external_facility_id)
  id / created_at / updated_at は DB default に委ねる（seed で指定しない）。

マッピング・契約の正本は docs/design/supabase-care-integration.md。

## Data Integrity（免除なし）

  - 入力件数 → 出力件数を assert（不一致は非 0 exit）。
  - external_facility_id（=office_id）の重複を検出（複合一意契約）。dedupe した
    場合は差分件数と理由を stdout に明示。本データでは重複 0 が期待値。

## 出力仕様（docs/design と一致）

  - JSONL: dist/supabase/care_facilities_seed.jsonl（UTF-8 / LF / null は JSON null）
  - SQL:   dist/supabase/care_facilities_seed.sql（upsert・on conflict do update）

Usage:
    python scripts/export_supabase_seed.py
Exit code: 0 = green / 非 0 = 件数不整合等の fail（deploy ゲート互換）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows のデフォルト stdout（cp932）で日本語ログが化ける環境向けに UTF-8 固定。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data" / "normalized" / "offices_430.json"
OUT_DIR = REPO_ROOT / "dist" / "supabase"
OUT_JSONL = OUT_DIR / "care_facilities_seed.jsonl"
OUT_SQL = OUT_DIR / "care_facilities_seed.sql"

SERVICE_KEY = "care"

# facilities 列 → offices_430.json フィールドの対応（docs/design §1-1 と一致）。
# id / created_at / updated_at は DB default に委ねるため含めない。
FIELD_MAP = [
    ("external_facility_id", "office_id"),
    ("facility_name", "name"),
    ("postal_code", "postal_code"),
    ("prefecture", "prefecture"),
    ("city", "city"),
    ("address_line1", "address"),
    ("address_line2", "address_building"),
]
# SQL の insert 列順（service_key を先頭に付与）。
SQL_COLUMNS = ["service_key"] + [col for col, _ in FIELD_MAP]


def norm(v: object) -> object:
    """空文字は null 扱いに正規化（facilities は nullable 列。空文字を送らない）。"""
    if v is None:
        return None
    if isinstance(v, str) and v == "":
        return None
    return v


def to_record(row: dict) -> dict:
    rec = {"service_key": SERVICE_KEY}
    for col, src in FIELD_MAP:
        rec[col] = norm(row.get(src))
    return rec


def sql_literal(v: object) -> str:
    if v is None:
        return "null"
    # facilities の対象列はすべて text。文字列化してシングルクォートエスケープ。
    s = str(v)
    return "'" + s.replace("'", "''") + "'"


def build_sql(records: list[dict]) -> str:
    cols = ", ".join(SQL_COLUMNS)
    # do update: facility_name / postal_code / prefecture / city / address_line1/2 を更新。
    update_cols = [c for c in SQL_COLUMNS if c not in ("service_key", "external_facility_id")]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    lines = [
        "-- care_facilities_seed.sql — 生成物（自動生成・手編集しない）",
        "-- 生成元: scripts/export_supabase_seed.py / data/normalized/offices_430.json",
        "-- 接続先: public.facilities（zaitaku-members 006_facilities.sql）",
        "-- 投入は人間ゲート（admin 権限・院長 go）。本ファイル生成 = 投入ではない。",
        f"-- 件数: {len(records)} 行",
        "",
        "begin;",
    ]
    for rec in records:
        vals = ", ".join(sql_literal(rec[c]) for c in SQL_COLUMNS)
        lines.append(
            f"insert into public.facilities ({cols}) values ({vals}) "
            f"on conflict (service_key, external_facility_id) do update set {set_clause};"
        )
    lines.append("commit;")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not DATA_FILE.exists():
        print(f"[FAIL] 入力データが見つかりません: data/normalized/offices_430.json", file=sys.stderr)
        return 2

    with DATA_FILE.open(encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        print("[FAIL] 入力 JSON が list ではありません", file=sys.stderr)
        return 2

    input_count = len(rows)
    print(f"[OK] 入力件数（実測）: {input_count} 件")

    # 変換 + 一意性（複合一意契約: service_key='care' × external_facility_id）検証。
    records = []
    seen = set()
    dup_count = 0
    empty_id = 0
    for row in rows:
        rec = to_record(row)
        ext_id = rec["external_facility_id"]
        if ext_id in (None, ""):
            empty_id += 1
            continue
        if ext_id in seen:
            dup_count += 1
            continue  # dedupe: 複合一意違反を避ける（本データでは 0 が期待値）
        seen.add(ext_id)
        records.append(rec)

    output_count = len(records)
    if empty_id:
        print(f"[WARN] external_facility_id 空の行を除外: {empty_id} 件")
    if dup_count:
        print(f"[WARN] external_facility_id 重複を dedupe: {dup_count} 件（複合一意契約のため先勝ち）")
    else:
        print("[OK] external_facility_id 重複なし（複合一意契約を満たす）")

    # Data Integrity: 件数 before/after。dedupe/除外がなければ厳密一致を要求。
    expected = input_count - dup_count - empty_id
    assert output_count == expected, (
        f"件数不整合: output={output_count} != input({input_count}) - dup({dup_count}) - empty({empty_id})"
    )
    print(f"[OK] 件数照合: input({input_count}) - dup({dup_count}) - empty({empty_id}) == output({output_count})")

    # 出力（UTF-8 / LF）。
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[OK] JSONL 出力: dist/supabase/care_facilities_seed.jsonl（{output_count} 行）")

    with OUT_SQL.open("w", encoding="utf-8", newline="\n") as f:
        f.write(build_sql(records))
    print(f"[OK] SQL 出力: dist/supabase/care_facilities_seed.sql（{output_count} 行・upsert）")

    # 出力ファイルの行数と records 件数の一致を再検証（成果物間の件数一致）。
    with OUT_JSONL.open(encoding="utf-8") as f:
        jsonl_lines = sum(1 for _ in f)
    assert jsonl_lines == output_count, f"JSONL 行数({jsonl_lines}) != records({output_count})"
    print(f"[OK] 成果物件数一致: JSONL 行数({jsonl_lines}) == records({output_count})")

    print(f"\n=== summary: input={input_count} output={output_count} dup={dup_count} empty={empty_id} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
