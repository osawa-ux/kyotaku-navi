"""
居宅介護支援事業所ナビ 一気通しパイプライン

download → normalize → build を1コマンドで実行する。

使い方:
  python scripts/run_pipeline.py                   # フル実行
  python scripts/run_pipeline.py --skip-download    # ダウンロード省略
  python scripts/run_pipeline.py --skip-normalize   # 正規化省略
  python scripts/run_pipeline.py --skip-build       # ビルド省略
  python scripts/run_pipeline.py --from normalize   # 正規化から開始
  python scripts/run_pipeline.py --from build       # ビルドのみ
  python scripts/run_pipeline.py --clean            # dist/ を削除してからビルド
  python scripts/run_pipeline.py --preview          # ビルド後にローカルサーバー起動

パス構成:
  download_csv.py → data_sources/mhlw/raw_jigyosho_430.csv
                  ↓ (コピー)
  normalize.py    ← data/raw/jigyosho_430.csv
                  → data/normalized/offices_430.json
  build_site.py   ← data/normalized/offices_430.json
                  → dist/
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = sys.executable  # 実行中のPythonインタプリタ

# --- パス定義 ---
DOWNLOAD_SCRIPT = BASE_DIR / "scripts" / "download_csv.py"
NORMALIZE_SCRIPT = BASE_DIR / "scripts" / "normalize.py"
BUILD_SCRIPT = BASE_DIR / "build_site.py"

# download_csv.py の出力先
DOWNLOAD_OUTPUT = BASE_DIR / "data_sources" / "mhlw" / "raw_jigyosho_430.csv"
# normalize.py の入力（download出力からコピーして揃える）
NORMALIZE_INPUT = BASE_DIR / "data" / "raw" / "jigyosho_430.csv"
# normalize.py の出力
NORMALIZE_OUTPUT = BASE_DIR / "data" / "normalized" / "offices_430.json"
# build_site.py の出力
DIST_DIR = BASE_DIR / "dist"


def log(step, total, msg):
    print(f"[{step}/{total}] {msg}")


def log_ok(msg):
    print(f"  OK: {msg}")


def log_err(msg):
    print(f"  ERROR: {msg}", file=sys.stderr)


def run_script(script_path, args=None, verbose=False):
    """Pythonスクリプトを subprocess で実行する。失敗時は例外"""
    cmd = [PYTHON, str(script_path)]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    kwargs = {
        "cwd": str(BASE_DIR),
        "env": env,
    }
    if not verbose:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT

    start = time.time()
    result = subprocess.run(cmd, **kwargs)
    elapsed = time.time() - start

    if result.returncode != 0:
        # 失敗時はログを表示
        if not verbose and result.stdout:
            print(result.stdout.decode("utf-8", errors="replace"))
        raise RuntimeError(
            f"{script_path.name} が終了コード {result.returncode} で失敗 ({elapsed:.1f}秒)"
        )

    output = ""
    if not verbose and result.stdout:
        output = result.stdout.decode("utf-8", errors="replace")

    return output, elapsed


# ============================================================
# ステップ実装
# ============================================================

def step_download(verbose=False):
    """Step 1: CSVダウンロード"""
    output, elapsed = run_script(DOWNLOAD_SCRIPT, ["--force"], verbose=verbose)

    if not DOWNLOAD_OUTPUT.exists():
        raise RuntimeError(f"ダウンロード出力が見つかりません: {DOWNLOAD_OUTPUT}")

    # normalize.py の入力パスにコピー
    NORMALIZE_INPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOWNLOAD_OUTPUT, NORMALIZE_INPUT)

    size_mb = DOWNLOAD_OUTPUT.stat().st_size / 1024 / 1024
    log_ok(f"CSV取得完了 ({size_mb:.1f} MB, {elapsed:.1f}秒)")

    if not verbose and output:
        # 件数だけ抽出
        for line in output.splitlines():
            if "総件数" in line or "total" in line.lower():
                print(f"  {line.strip()}")
                break


def step_normalize(verbose=False):
    """Step 2: CSV正規化"""
    if not NORMALIZE_INPUT.exists():
        # download出力からコピーを試みる
        if DOWNLOAD_OUTPUT.exists():
            NORMALIZE_INPUT.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DOWNLOAD_OUTPUT, NORMALIZE_INPUT)
            log_ok(f"CSVをコピー: {DOWNLOAD_OUTPUT.name} → {NORMALIZE_INPUT}")
        else:
            raise RuntimeError(
                f"入力CSVが見つかりません: {NORMALIZE_INPUT}\n"
                f"  先に download を実行するか、--from download で開始してください。"
            )

    output, elapsed = run_script(NORMALIZE_SCRIPT, verbose=verbose)

    if not NORMALIZE_OUTPUT.exists():
        raise RuntimeError(f"正規化出力が見つかりません: {NORMALIZE_OUTPUT}")

    # 件数を取得
    with open(NORMALIZE_OUTPUT, encoding="utf-8") as f:
        records = json.load(f)
    count = len(records)
    log_ok(f"{count:,}件 正規化完了 ({elapsed:.1f}秒)")

    if not verbose and output:
        for line in output.splitlines():
            if "office_id重複" in line or "都道府県数" in line:
                print(f"  {line.strip()}")

    return count


def step_build(verbose=False, preview=False):
    """Step 3: 静的サイト生成"""
    if not NORMALIZE_OUTPUT.exists():
        raise RuntimeError(
            f"正規化済みJSONが見つかりません: {NORMALIZE_OUTPUT}\n"
            f"  先に normalize を実行してください。"
        )

    args = []
    if preview:
        args.append("--preview")

    output, elapsed = run_script(BUILD_SCRIPT, args, verbose=verbose)

    if not (DIST_DIR / "index.html").exists():
        raise RuntimeError("ビルド出力が見つかりません: dist/index.html")

    log_ok(f"静的サイト生成完了 ({elapsed:.1f}秒)")

    if not verbose and output:
        for line in output.splitlines():
            if "生成完了" in line or "チェック" in line or "OK" in line:
                print(f"  {line.strip()}")


# ============================================================
# 検証
# ============================================================

def verify():
    """ビルド成果物の検証"""
    print()
    print("=" * 60)
    print("  パイプライン検証")
    print("=" * 60)

    checks = []

    def check(name, condition, detail=""):
        status = "OK" if condition else "FAIL"
        checks.append((name, condition))
        msg = f"  [{status:4s}] {name}"
        if detail:
            msg += f" ({detail})"
        print(msg)

    # ファイル存在チェック
    check("data/raw/jigyosho_430.csv", NORMALIZE_INPUT.exists())
    check("data/normalized/offices_430.json", NORMALIZE_OUTPUT.exists())
    check("dist/index.html", (DIST_DIR / "index.html").exists())
    check("dist/sitemap.xml", (DIST_DIR / "sitemap.xml").exists())
    check("dist/robots.txt", (DIST_DIR / "robots.txt").exists())

    # 検索JSON 47ファイル
    search_dir = DIST_DIR / "data" / "search"
    search_count = len(list(search_dir.glob("*.json"))) if search_dir.exists() else 0
    check("search JSON 47ファイル", search_count == 47, f"{search_count}ファイル")

    # geo JSON
    geo_path = DIST_DIR / "data" / "offices_geo.json"
    check("offices_geo.json", geo_path.exists())

    # 件数整合チェック
    normalized_count = 0
    if NORMALIZE_OUTPUT.exists():
        with open(NORMALIZE_OUTPUT, encoding="utf-8") as f:
            normalized_count = len(json.load(f))

    office_pages = len(list((DIST_DIR / "office").glob("*.html"))) if (DIST_DIR / "office").exists() else 0
    check(
        "詳細ページ数 = 正規化件数",
        office_pages == normalized_count,
        f"pages={office_pages:,} normalized={normalized_count:,}",
    )

    pref_pages = len(list((DIST_DIR / "pref").glob("*.html"))) if (DIST_DIR / "pref").exists() else 0
    check("都道府県ページ = 47", pref_pages == 47, f"{pref_pages}")

    # stats.json 整合
    stats_path = DIST_DIR / "data" / "stats.json"
    if stats_path.exists():
        with open(stats_path, encoding="utf-8") as f:
            stats = json.load(f)
        stats_total = stats.get("total", 0)
        check("stats.json 件数整合", stats_total == normalized_count,
              f"stats={stats_total:,} normalized={normalized_count:,}")

    print("=" * 60)
    failed = sum(1 for _, ok in checks if not ok)
    if failed:
        print(f"  {failed}件の検証が失敗しました")
    else:
        print(f"  全{len(checks)}項目 通過")
    print("=" * 60)

    return failed == 0


# ============================================================
# メイン
# ============================================================

def main():
    args = sys.argv[1:]

    skip_download = "--skip-download" in args
    skip_normalize = "--skip-normalize" in args
    skip_build = "--skip-build" in args
    clean = "--clean" in args
    preview = "--preview" in args
    verbose = "--verbose" in args

    # --from オプション
    from_step = None
    for i, a in enumerate(args):
        if a == "--from" and i + 1 < len(args):
            from_step = args[i + 1]
            break

    if from_step:
        steps_order = ["download", "normalize", "build"]
        if from_step not in steps_order:
            print(f"ERROR: --from の値は {steps_order} のいずれかにしてください")
            sys.exit(1)
        idx = steps_order.index(from_step)
        if idx > 0:
            skip_download = True
        if idx > 1:
            skip_normalize = True

    do_download = not skip_download
    do_normalize = not skip_normalize
    do_build = not skip_build

    steps = []
    if do_download:
        steps.append("download")
    if do_normalize:
        steps.append("normalize")
    if do_build:
        steps.append("build")

    if not steps:
        print("ERROR: 全ステップがスキップされました。実行するステップがありません。")
        sys.exit(1)

    total = len(steps)
    print(f"=== 居宅介護支援ナビ パイプライン ===")
    print(f"実行ステップ: {' → '.join(steps)}")
    if clean:
        print(f"--clean: dist/ を削除します")
    print()

    start_all = time.time()
    step_num = 0

    try:
        # Clean
        if clean and DIST_DIR.exists():
            shutil.rmtree(DIST_DIR)
            print(f"dist/ を削除しました")

        # Step 1: Download
        if do_download:
            step_num += 1
            log(step_num, total, "CSVダウンロード...")
            step_download(verbose=verbose)

        # Step 2: Normalize
        if do_normalize:
            step_num += 1
            log(step_num, total, "CSV正規化...")
            step_normalize(verbose=verbose)

        # Step 3: Build
        if do_build:
            step_num += 1
            log(step_num, total, "静的サイト生成...")
            step_build(verbose=verbose, preview=preview)

    except RuntimeError as e:
        log_err(str(e))
        print(f"\nパイプライン失敗: ステップ {step_num}/{total} で停止")
        sys.exit(1)
    except Exception as e:
        log_err(f"予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        print(f"\nパイプライン失敗: ステップ {step_num}/{total} で停止")
        sys.exit(1)

    elapsed_all = time.time() - start_all

    # 検証（build を実行した場合のみ）
    if do_build:
        verify_ok = verify()
    else:
        verify_ok = True

    # サマリー
    print()
    print(f"=== パイプライン完了 ({elapsed_all:.1f}秒) ===")
    if NORMALIZE_OUTPUT.exists():
        with open(NORMALIZE_OUTPUT, encoding="utf-8") as f:
            count = len(json.load(f))
        print(f"  事業所数: {count:,}件")
    if do_build and (DIST_DIR / "office").exists():
        pages = len(list((DIST_DIR / "office").glob("*.html")))
        print(f"  詳細ページ: {pages:,}枚")
    if do_build:
        print(f"  出力先: {DIST_DIR}/")
    if not verify_ok:
        print(f"  [WARN] 一部の検証が失敗しています")
        sys.exit(1)


if __name__ == "__main__":
    main()
