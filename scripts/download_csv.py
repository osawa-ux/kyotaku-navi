"""
厚生労働省 介護サービス情報公表システム オープンデータCSVのダウンロードと基本分析

データソース: https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html
ライセンス: CC BY 4.0（出典明記で商用利用可）
対象: jigyosho_430.csv（居宅介護支援、サービスコード430）

使い方:
  python scripts/download_csv.py          # ダウンロード + 分析
  python scripts/download_csv.py --force  # 既存ファイルを上書き
  python scripts/download_csv.py --skip-download  # 既存ファイルで分析のみ
"""

import csv
import hashlib
import json
import os
import sys
from datetime import datetime
import unicodedata

import requests

# === 設定 ===
CSV_URL = "https://www.mhlw.go.jp/content/12300000/jigyosho_430.csv"
SERVICE_CODE = "430"
SERVICE_NAME = "居宅介護支援"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "data_sources", "mhlw")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "raw_jigyosho_430.csv")
REPORT_DIR = os.path.join(BASE_DIR, "data_sources", "reports")

# 最低期待件数（この件数を下回ったらWARN）
EXPECTED_MIN_ROWS = 35000


def download_csv() -> str:
    """CSVをダウンロードして保存する。保存先パスを返す。"""
    print(f"ダウンロード中: {CSV_URL}")
    try:
        r = requests.get(CSV_URL, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] ダウンロード失敗: {e}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(r.content)

    size_mb = len(r.content) / 1024 / 1024
    file_hash = hashlib.sha256(r.content).hexdigest()

    print(f"保存完了: {OUTPUT_PATH}")
    print(f"  サイズ: {size_mb:.1f} MB")
    print(f"  SHA256: {file_hash}")
    return OUTPUT_PATH


def analyze_csv(filepath: str) -> dict:
    """CSVの基本分析を実行し、レポートを返す。"""

    # utf-8-sig = BOM付きUTF-8（厚労省CSVの文字コード）
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    total = len(rows)
    cols = header  # カラム名リスト

    print("\n" + "=" * 60)
    print(f"  {SERVICE_NAME} オープンデータCSV 分析レポート")
    print("=" * 60)
    print(f"ファイル: {os.path.basename(filepath)}")
    print(f"文字コード: UTF-8 BOM付き (utf-8-sig)")
    print(f"総件数: {total:,}件")
    print(f"カラム数: {len(cols)}")
    print(f"分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # --- カラム別充填率 ---
    print("\n--- カラム別充填率 ---")
    fill_rates = {}
    for i, col in enumerate(cols):
        filled = sum(1 for row in rows if i < len(row) and row[i].strip() != "")
        rate = filled / total * 100 if total > 0 else 0
        fill_rates[col] = rate
        mark = "OK  " if rate >= 95 else "LOW " if rate >= 50 else "WARN"
        print(f"  [{mark}] [{i:2d}] {col}: {rate:.1f}% ({filled:,}/{total:,})")

    # --- 都道府県別件数 ---
    print("\n--- 都道府県別件数 ---")
    pref_col_idx = 2  # 都道府県名
    pref_counts: dict[str, int] = {}
    for row in rows:
        pref = row[pref_col_idx] if len(row) > pref_col_idx else ""
        pref_counts[pref] = pref_counts.get(pref, 0) + 1

    pref_data = {}
    for pref_name in sorted(pref_counts.keys()):
        count = pref_counts[pref_name]
        pref_data[pref_name] = count
        print(f"  {pref_name}: {count:,}件")
    print(f"\n  都道府県数: {len(pref_counts)}")
    print(f"  合計: {sum(pref_counts.values()):,}件")

    # --- 重要統計 ---
    print("\n--- 重要統計 ---")

    # 事業所番号の重複
    office_code_idx = 15
    office_codes = [row[office_code_idx] for row in rows if len(row) > office_code_idx]
    dup_count = len(office_codes) - len(set(office_codes))
    mark = "OK  " if dup_count == 0 else "WARN"
    print(f"  [{mark}] 事業所番号の重複: {dup_count}件")

    # 緯度経度の充填
    geo_count = sum(
        1 for row in rows
        if len(row) > 10 and row[9].strip() != "" and row[10].strip() != ""
    )
    mark = "OK  " if geo_count == total else "WARN"
    print(f"  [{mark}] 緯度経度あり: {geo_count:,}件 ({geo_count/total*100:.1f}%)")

    # URL保有率
    url_col_idx = 19
    url_count_raw = sum(1 for row in rows if len(row) > url_col_idx and row[url_col_idx].strip() != "")
    url_count_valid = sum(
        1 for row in rows
        if len(row) > url_col_idx and row[url_col_idx].strip().startswith(("http://", "https://"))
    )
    print(f"  [INFO] URL列に値あり: {url_count_raw:,}件 ({url_count_raw/total*100:.1f}%)")
    print(f"  [INFO] 有効URL (http/https): {url_count_valid:,}件 ({url_count_valid/total*100:.1f}%)")
    if url_count_raw - url_count_valid > 0:
        print(f"  [WARN] URL列にメール等の無効値: {url_count_raw - url_count_valid}件（正規化時に除外）")

    # 定員0の割合（居宅介護支援は実質定員制限なし）
    cap_col_idx = 18
    cap_zero = sum(
        1 for row in rows
        if len(row) > cap_col_idx and row[cap_col_idx].strip() in ("0", "")
    )
    print(f"  [INFO] 定員=0または空欄（未設定）: {cap_zero:,}件 ({cap_zero/total*100:.1f}%)")

    # 法人種別の分布
    corp_col_idx = 14
    corps = [row[corp_col_idx] for row in rows if len(row) > corp_col_idx and row[corp_col_idx].strip()]
    corp_types = {
        "医療法人": sum(1 for c in corps if "医療法人" in c),
        "株式会社": sum(1 for c in corps if "株式会社" in c),
        "有限会社": sum(1 for c in corps if "有限会社" in c),
        "社会福祉法人": sum(1 for c in corps if "社会福祉法人" in c),
        "NPO法人/特定非営利": sum(1 for c in corps if "特定非営利" in c or "NPO" in c),
        "合同会社": sum(1 for c in corps if "合同会社" in c),
        "一般社団法人": sum(1 for c in corps if "一般社団法人" in c),
    }
    print("\n--- 法人種別分布 ---")
    for ctype, count in sorted(corp_types.items(), key=lambda x: -x[1]):
        print(f"  {ctype}: {count:,}件 ({count/total*100:.1f}%)")

    # --- レポートJSON保存 ---
    report = {
        "analyzed_at": datetime.now().isoformat(),
        "service_code": SERVICE_CODE,
        "service_name": SERVICE_NAME,
        "file": os.path.basename(filepath),
        "total_records": total,
        "columns": len(cols),
        "column_names": cols,
        "fill_rates": {k: round(v, 1) for k, v in fill_rates.items()},
        "prefecture_counts": {k: int(v) for k, v in pref_data.items()},
        "prefecture_count": len(pref_counts),
        "duplicated_office_codes": dup_count,
        "geo_available": geo_count,
        "url_raw": url_count_raw,
        "url_valid": url_count_valid,
        "corporation_types": {k: int(v) for k, v in corp_types.items()},
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "csv_analysis_430.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nレポート保存: {report_path}")

    return report


def validate_report(report: dict) -> bool:
    """分析結果を検証し、問題があれば警告を出す。Trueなら正常。"""
    total = report["total_records"]
    ok = True

    print("\n" + "=" * 60)
    print("  データ品質 最終チェック")
    print("=" * 60)

    # 件数チェック
    if total < EXPECTED_MIN_ROWS:
        print(f"  [WARN] 総件数が想定より少ない: {total:,}件 (期待値: {EXPECTED_MIN_ROWS:,}件以上)")
        ok = False
    else:
        print(f"  [OK  ] 総件数: {total:,}件")

    # 都道府県数チェック
    pref_count = report.get("prefecture_count", 0)
    if pref_count < 47:
        print(f"  [WARN] 都道府県数が47未満: {pref_count}都道府県")
        ok = False
    else:
        print(f"  [OK  ] 都道府県数: {pref_count}都道府県")

    # 事業所番号重複チェック
    dup = report.get("duplicated_office_codes", -1)
    if dup != 0:
        print(f"  [WARN] 事業所番号の重複: {dup}件")
        ok = False
    else:
        print(f"  [OK  ] 事業所番号の重複: なし")

    # 緯度経度チェック（100%のはず）
    geo = report.get("geo_available", 0)
    if geo < total:
        print(f"  [WARN] 緯度経度の欠損: {total - geo}件")
    else:
        print(f"  [OK  ] 緯度経度: 全件あり")

    print("=" * 60)
    if not ok:
        print("  [WARN] 上記の警告を確認してから次工程を進めてください")
    else:
        print("  [OK] データ品質チェック通過 — 正規化処理へ進めます")
    print("=" * 60)

    return ok


def main():
    skip_download = "--skip-download" in sys.argv
    force = "--force" in sys.argv

    # ダウンロード
    if skip_download:
        if not os.path.exists(OUTPUT_PATH):
            print(f"[ERROR] ファイルが存在しません: {OUTPUT_PATH}")
            sys.exit(1)
        print(f"既存ファイル使用: {OUTPUT_PATH}")
        filepath = OUTPUT_PATH
    elif os.path.exists(OUTPUT_PATH) and not force:
        print(f"既存ファイル使用: {OUTPUT_PATH}")
        print("  (再ダウンロードは --force オプションを使用)")
        filepath = OUTPUT_PATH
    else:
        filepath = download_csv()

    # 分析
    report = analyze_csv(filepath)

    # 検証
    validate_report(report)


if __name__ == "__main__":
    main()
