#!/usr/bin/env python3
"""validate_data.py — kyotaku-navi データ整合性チェック（lightweight, 標準ライブラリのみ）

CLAUDE.md 「Data Integrity Check」を機械化したもの。deploy ゲートに組み込める形
（exit code 0 = green / 非0 = fail）。

## 件数の関係式（実測で裏取り済み・FAIL 対象）

データ源: data/normalized/offices_430.json（list, 1 レコード = 1 事業所×サービス）

  - detail_html_count (dist/caremanager/*.html) == data_record_count + 1
      dist/caremanager/ には各事業所の詳細ページに加え index.html（一覧ページ）が
      1 枚含まれるため「+1」。2026-07-06 実測: 36,492 == 36,491 + 1 で一致確認済み。
  - search_json_total (dist/data/search/{01..47}.json の合計件数) == data_record_count
      都道府県別 search JSON の合計は detail ページと異なり index を含まないため
      オフセットなしの完全一致。2026-07-06 実測: 36,491 == 36,491 で一致確認済み。

上記 2 式は実データで裏取り済みのため FAIL 条件にしている。

## WARN 止まりの項目（関係式が未確定）

  - sitemap.xml の <loc> 数、dist 内 HTML 総数: pref/city ページ・static ページ等
    detail 以外の URL も多数含まれており、data_record_count との厳密な関係式が
    未確定。回帰検知の目的で baseline には記録するが、単独では FAIL 条件にしない。

## baseline ファイル

scripts/validation_baseline.json（このrepo内・PHI なし・件数と実行時刻のみ）。
git 管理は人間判断（commit/push はこの script の責務外）。初回実行時は記録のみ、
2 回目以降は前回との差分が 5% 超の減少で FAIL、5% 以下の減少で WARN。

## 前提

dist/ はビルド出力（.gitignore 対象・build_site.py 実行後にのみ存在）。
dist/ が存在しない場合は「未ビルド」として exit 0 + メッセージで skip する
（run_pipeline.py への組込は行わず、独立スクリプトとして deploy 前に手動 or
CI/deploy スクリプトから呼び出す運用を想定 — 理由は README 参照）。

Usage:
    python scripts/validate_data.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows のデフォルト stdout エンコーディング（cp932）だと日本語ログが文字化けする
# 環境があるため、UTF-8 に固定する（CI の Ubuntu ランナー等では no-op）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data" / "normalized" / "offices_430.json"
DIST_DIR = REPO_ROOT / "dist"
DETAIL_DIR = DIST_DIR / "caremanager"
SEARCH_DIR = DIST_DIR / "data" / "search"
SITEMAP_FILE = DIST_DIR / "sitemap.xml"
BASELINE_FILE = REPO_ROOT / "scripts" / "validation_baseline.json"

# offices_master の required:true フィールド（config/schema.yaml 実態から確定）
REQUIRED_FIELDS = [
    "office_id", "portal_type", "service_code", "service_name", "name",
    "prefecture", "pref_code", "city", "address", "office_code",
    "source_primary", "is_active",
]

BASELINE_DROP_FAIL_RATIO = 0.05  # 5% 超の減少で FAIL

results: list[tuple[str, str]] = []  # (level, message) level in {"OK", "WARN", "FAIL"}


def log(level: str, message: str) -> None:
    results.append((level, message))
    print(f"[{level}] {message}")


def load_data() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def count_html_files(directory: Path, exclude_names: set[str] = frozenset()) -> int:
    if not directory.exists():
        return 0
    n = 0
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix == ".html" and entry.name not in exclude_names:
            n += 1
    return n


def count_html_files_recursive(directory: Path) -> int:
    if not directory.exists():
        return 0
    n = 0
    for p in directory.rglob("*.html"):
        if p.is_file():
            n += 1
    return n


def sum_search_json(directory: Path) -> int:
    if not directory.exists():
        return 0
    total = 0
    for f in sorted(directory.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            total += len(json.load(fh))
    return total


def count_sitemap_locs(sitemap_file: Path) -> int:
    if not sitemap_file.exists():
        return 0
    text = sitemap_file.read_text(encoding="utf-8")
    return len(re.findall(r"<loc>", text))


def check_required_fields(records: list[dict]) -> None:
    missing_total = 0
    per_field: dict[str, int] = {}
    for field in REQUIRED_FIELDS:
        missing = sum(1 for r in records if not r.get(field) and r.get(field) != 0 and r.get(field) is not False)
        if missing:
            per_field[field] = missing
            missing_total += missing
    if missing_total == 0:
        log("OK", f"必須フィールド欠落チェック: 欠落なし（{len(REQUIRED_FIELDS)} フィールド確認）")
    else:
        detail = ", ".join(f"{k}={v}件" for k, v in per_field.items())
        log("WARN", f"必須フィールド欠落あり（新規チェックにつき FAIL 条件にはしない・要人手確認）: {detail}")


def check_internal_link_spot(site_dir: Path) -> None:
    """代表ページ数件の href（サイトルート相対 '/...'）が生成物内に実在するか軽量確認。全ページ走査はしない。"""
    if not site_dir.exists():
        log("WARN", "internal link spot check: dist が存在しないためスキップ")
        return

    candidates: list[Path] = []
    top = site_dir / "index.html"
    if top.exists():
        candidates.append(top)
    pref_dir = site_dir / "pref"
    if pref_dir.exists():
        for p in sorted(pref_dir.glob("*.html"))[:1]:
            candidates.append(p)
    detail_dir = site_dir / "caremanager"
    if detail_dir.exists():
        for entry in detail_dir.iterdir():
            if entry.is_file() and entry.suffix == ".html" and entry.name != "index.html":
                candidates.append(entry)
                break

    if not candidates:
        log("WARN", "internal link spot check: 代表ページが見つからずスキップ")
        return

    checked = 0
    broken: list[str] = []
    from urllib.parse import unquote

    def href_resolves(href: str) -> bool:
        """href の解決を試みる。生成物によってファイル名が生 UTF-8 のもの
        （kango/welfare 系）と %XX percent-encoded のまま保存されるもの
        （このrepoの build_site.py）が混在するため、両方を試す。"""
        path_part = href.split("?")[0]
        rel_candidates = [path_part.lstrip("/"), unquote(path_part).lstrip("/")]
        for rel in rel_candidates:
            if rel == "":
                rel = "index.html"
            elif rel.endswith("/"):
                rel = rel + "index.html"
            if (site_dir / rel).exists():
                return True
        return False

    for page in candidates:
        html = page.read_text(encoding="utf-8", errors="replace")
        hrefs = [h for h in re.findall(r'href="(/[^"#]*)"', html) if not h.startswith("//")]
        # 1 ページあたり最大 10 件だけ確認（軽量 spot check）
        for href in hrefs[:10]:
            checked += 1
            if not href_resolves(href):
                broken.append(f"{page.relative_to(site_dir)} -> {href}")

    if broken:
        log("WARN", f"internal link spot check: {checked} 件中 {len(broken)} 件のリンク切れ疑い: {broken[:5]}")
    else:
        log("OK", f"internal link spot check: {len(candidates)} 代表ページ・{checked} href を確認、リンク切れなし")


def check_baseline(metrics: dict[str, int]) -> None:
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    if BASELINE_FILE.exists():
        try:
            previous = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None

    if previous is None:
        log("OK", f"baseline: 初回記録（{BASELINE_FILE.name} に保存）")
    else:
        prev_metrics = previous.get("metrics", {})
        for key, current_value in metrics.items():
            prev_value = prev_metrics.get(key)
            if prev_value is None or prev_value == 0:
                continue
            if current_value >= prev_value:
                continue
            drop_ratio = (prev_value - current_value) / prev_value
            if drop_ratio > BASELINE_DROP_FAIL_RATIO:
                log("FAIL", f"baseline 差分: {key} が {prev_value} → {current_value}（{drop_ratio:.1%} 減少・5%超）")
            else:
                log("WARN", f"baseline 差分: {key} が {prev_value} → {current_value}（{drop_ratio:.1%} 減少）")

    # ラチェットガード（reviewer 指摘 2026-07-06）: FAIL 検出時は baseline を上書きしない。
    # 上書きすると件数減少 FAIL が naive リトライで緑化し「件数減少=停止」の警報が消えるため、
    # FAIL ゼロのときのみ現在値を新 baseline として記録する。
    if any(level == "FAIL" for level, _ in results):
        log("WARN", "baseline: FAIL 検出のため更新せず（解消後の実行で更新される）")
        return
    import datetime
    BASELINE_FILE.write_text(
        json.dumps({"last_run": datetime.datetime.now().isoformat(), "metrics": metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} が存在しません。")
        return 1

    records = load_data()
    data_count = len(records)
    log("OK", f"データ件数（実測）: {data_count}件")

    if not DIST_DIR.exists():
        log("OK", "dist/ が存在しません（未ビルド）。件数整合チェックは skip します。")
        # baseline にはデータ件数のみ記録して終了（detail 系は 0 のためチェック不能）
        check_baseline({"data_record_count": data_count})
        return 0

    detail_count = count_html_files(DETAIL_DIR, exclude_names={"index.html"})
    detail_count_with_index = count_html_files(DETAIL_DIR)
    search_total = sum_search_json(SEARCH_DIR)
    sitemap_locs = count_sitemap_locs(SITEMAP_FILE)
    total_html = count_html_files_recursive(DIST_DIR)

    log("OK", f"detail HTML 件数（index.html 含む）: {detail_count_with_index}件 / 除く: {detail_count}件")
    log("OK", f"search JSON 合計件数: {search_total}件")
    log("OK", f"sitemap <loc> 数: {sitemap_locs}件 / dist 全 HTML: {total_html}件（関係式未確定・参考値）")

    # --- FAIL 条件（関係式が裏取り済みの項目のみ）---
    expected_detail = data_count + 1
    if detail_count_with_index == expected_detail:
        log("OK", f"件数整合: detail_html({detail_count_with_index}) == data({data_count}) + 1")
    else:
        log("FAIL", f"件数整合 NG: detail_html({detail_count_with_index}) != data({data_count}) + 1 (={expected_detail})")

    if search_total == data_count:
        log("OK", f"件数整合: search_json_total({search_total}) == data({data_count})")
    else:
        log("FAIL", f"件数整合 NG: search_json_total({search_total}) != data({data_count})")

    check_required_fields(records)
    check_internal_link_spot(DIST_DIR)

    metrics = {
        "data_record_count": data_count,
        "detail_html_count": detail_count_with_index,
        "search_json_total": search_total,
        "sitemap_loc_count": sitemap_locs,
        "total_html_count": total_html,
    }
    check_baseline(metrics)

    fail_count = sum(1 for level, _ in results if level == "FAIL")
    warn_count = sum(1 for level, _ in results if level == "WARN")
    print(f"\n=== summary: FAIL={fail_count} WARN={warn_count} OK={len(results) - fail_count - warn_count} ===")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
