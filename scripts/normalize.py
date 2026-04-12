"""
厚労省オープンデータ jigyosho_430.csv → 正規化済み JSON/JSONL 変換

入力: data/raw/jigyosho_430.csv
出力:
  data/normalized/offices_430.jsonl  (1行1レコード、主出力)
  data/normalized/offices_430.json   (配列形式、副出力)

正規化ルール:
  - 文字列: NFKC正規化、前後空白除去、空文字→null
  - 電話/FAX: 元データ維持（既にハイフン付き）。非電話番号→null
  - URL: http/https のみ有効、それ以外→null
  - 緯度経度: float化、不正値→null
  - 定員: 0→null（居宅介護支援は実質定員制限なし）
  - office_id: "mhlw_kaigo:{office_code}:430"

データソース互換:
  訪問看護ナビ (houmonkango-navi) の normalize_stations.py と
  同一の正規化関数（zen_to_han, normalize_tel, normalize_postal 等）を流用。
  フィールド名は OfficeMaster スキーマに準拠。
"""

import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(BASE_DIR, "data", "raw", "jigyosho_430.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "normalized")
OUTPUT_JSONL = os.path.join(OUTPUT_DIR, "offices_430.jsonl")
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "offices_430.json")

# --- 固定値 ---
PORTAL_TYPE = "kyotaku"
SERVICE_CODE = "430"
SERVICE_NAME = "居宅介護支援"
SERVICE_CATEGORY = "caremanager"  # URL prefix。将来 home-help / day-service 等を追加
SOURCE_PRIMARY = "mhlw_kaigo_open_data"
SOURCE_URL = "https://www.mhlw.go.jp/content/12300000/jigyosho_430.csv"

JST = timezone(timedelta(hours=9))


# ============================================================
# 正規化ユーティリティ（訪問看護 normalize_stations.py から流用）
# ============================================================

def zen_to_han(text: str) -> str:
    """全角英数を半角に変換（NFKC正規化）"""
    if not isinstance(text, str):
        return text
    return unicodedata.normalize("NFKC", text)


def clean_str(val) -> str | None:
    """文字列を正規化して返す。空文字・NaN相当はNone"""
    if val is None:
        return None
    if not isinstance(val, str):
        val = str(val)
    val = zen_to_han(val).strip()
    # 連続空白を1つに
    val = re.sub(r"\s+", " ", val)
    if val == "" or val.lower() == "nan":
        return None
    return val


def normalize_tel(tel: str) -> str | None:
    """電話番号を正規化。非電話番号はNone。

    訪問看護 normalize_stations.py と同一ロジック。
    厚労省CSVは既にハイフン付きなので、基本は元値を維持する。
    """
    if not isinstance(tel, str) or not tel.strip():
        return None
    tel = zen_to_han(tel).strip()
    # 数字とハイフンのみ残す
    cleaned = re.sub(r"[^\d\-]", "", tel)
    # 最低限の電話番号チェック: 数字が10桁以上
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 10 or not digits.startswith("0"):
        return None
    # ハイフンなしの場合、パターンに応じてハイフン挿入
    if "-" not in cleaned and len(digits) >= 10:
        if digits.startswith("0120"):
            cleaned = f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
        elif digits.startswith("03") or digits.startswith("06"):
            cleaned = f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        elif digits.startswith("0"):
            cleaned = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return cleaned if cleaned else None


def normalize_url(url_val) -> str | None:
    """URLバリデーション。http/httpsのみ有効、それ以外はNone"""
    if not isinstance(url_val, str):
        return None
    url_val = zen_to_han(url_val).strip()
    if url_val.startswith(("http://", "https://")):
        return url_val
    return None


def parse_float(val) -> float | None:
    """float変換。不正値はNone"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).strip()
        if s == "" or s.lower() == "nan":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_capacity(val) -> int | None:
    """定員のパース。0は「未記入」扱いでNone"""
    if val is None:
        return None
    try:
        s = str(val).strip()
        if s == "" or s.lower() == "nan":
            return None
        n = int(float(s))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def parse_bool_flag(val) -> bool | None:
    """空欄→None、何か値があればTrue"""
    if not isinstance(val, str) or not val.strip():
        return None
    return True


def make_office_id(office_code: str) -> str:
    """office_id生成: mhlw_kaigo:{office_code}:430"""
    return f"mhlw_kaigo:{office_code}:{SERVICE_CODE}"


def derive_pref_code(city_code: str) -> str:
    """市区町村コード(6桁)の先頭2桁から都道府県コードを導出"""
    if city_code and len(city_code) >= 2:
        return city_code[:2]
    return ""


# ============================================================
# メイン処理
# ============================================================

def load_csv(path: str) -> tuple[list[str], list[list[str]]]:
    """CSVを読み込んでヘッダーと行リストを返す"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        # BOM除去（先頭カラム名のBOMが残る場合の対策）
        if header and header[0].startswith("\ufeff"):
            header[0] = header[0].lstrip("\ufeff")
        rows = list(reader)
    return header, rows


def normalize_row(row: list[str], cols: list[str], retrieved_at: str) -> dict:
    """1行のCSVデータを正規化済みdictに変換する

    CSVカラム配置（jigyosho_430.csv = jigyosho_130.csv と同一）:
      0: 都道府県コード又は市町村コード
      1: No（事業所番号と同値）
      2: 都道府県名
      3: 市区町村名
      4: 事業所名
      5: 事業所名カナ
      6: サービスの種類
      7: 住所
      8: 方書（ビル名等）
      9: 緯度
     10: 経度
     11: 電話番号
     12: FAX番号
     13: 法人番号
     14: 法人の名称
     15: 事業所番号
     16: 利用可能曜日
     17: 利用可能曜日特記事項
     18: 定員
     19: URL
     20: 高齢者の方と障害者の方が同時一体的に利用できるサービス
     21: 介護保険の通常の指定基準を満たしている
     22: 障害福祉の通常の指定基準を満たしている
     23: 備考
    """
    def col(i):
        return row[i] if i < len(row) else ""

    city_code = clean_str(col(0)) or ""
    office_code = clean_str(col(15)) or clean_str(col(1)) or ""
    pref_code = derive_pref_code(city_code)

    raw_name = col(4)
    raw_corp = col(14)
    raw_address = col(7)

    return {
        # --- 識別子 ---
        "office_id": make_office_id(office_code),
        "portal_type": PORTAL_TYPE,
        "service_code": SERVICE_CODE,
        "service_name": SERVICE_NAME,
        "service_category": SERVICE_CATEGORY,
        # --- 基本情報 ---
        "name": clean_str(raw_name),
        "name_kana": clean_str(col(5)),
        # --- 所在地 ---
        "prefecture": clean_str(col(2)),
        "pref_code": pref_code,
        "city": clean_str(col(3)),
        "city_code": city_code,
        "address": clean_str(raw_address),
        "address_building": clean_str(col(8)),
        "postal_code": None,  # 厚労省CSVには郵便番号なし
        # --- 連絡先 ---
        "tel": normalize_tel(col(11)),
        "fax": normalize_tel(col(12)),
        # --- 法人情報 ---
        "corporation_number": clean_str(col(13)),
        "corporation_name": clean_str(raw_corp),
        # --- 事業所番号 ---
        "office_code": office_code,
        # --- 地理情報 ---
        "latitude": parse_float(col(9)),
        "longitude": parse_float(col(10)),
        # --- Web ---
        "website_url": normalize_url(col(19)),
        # --- データソース ---
        "source_primary": SOURCE_PRIMARY,
        "source_url": SOURCE_URL,
        "source_updated_at": None,
        "retrieved_at": retrieved_at,
        # --- 状態 ---
        "is_active": True,
        # --- 居宅介護支援固有（KyotakuFeatures） ---
        "business_days_text": clean_str(col(16)),
        "business_days_note": clean_str(col(17)),
        "capacity": parse_capacity(col(18)),
        "inclusive_service": parse_bool_flag(col(20)),
        "meets_kaigo_standard": parse_bool_flag(col(21)),
        "meets_shogai_standard": parse_bool_flag(col(22)),
        "remarks_raw": clean_str(col(23)),
    }


def normalize_all(input_path: str) -> list[dict]:
    """CSV全件を正規化してレコードリストを返す"""
    print(f"[normalize] 入力: {input_path}")
    header, rows = load_csv(input_path)
    total_input = len(rows)
    print(f"[normalize] CSV読込: {total_input:,}件（カラム数: {len(header)}）")

    retrieved_at = datetime.now(JST).isoformat()
    records = []
    skipped = 0

    for i, row in enumerate(rows):
        rec = normalize_row(row, header, retrieved_at)
        # office_code が空の行はスキップ（破損行）
        if not rec["office_code"]:
            skipped += 1
            continue
        records.append(rec)

    if skipped > 0:
        print(f"[normalize] スキップ: {skipped}件（office_code空）")
    print(f"[normalize] 正規化完了: {len(records):,}件")
    return records


def write_outputs(records: list[dict]) -> dict:
    """JSONL + JSON の両方を書き出す"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # JSONL（主出力）
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[normalize] JSONL出力: {OUTPUT_JSONL} ({len(records):,}件)")

    # JSON配列（副出力）
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"[normalize] JSON出力: {OUTPUT_JSON} ({len(records):,}件)")

    return {
        "jsonl_path": OUTPUT_JSONL,
        "json_path": OUTPUT_JSON,
        "count": len(records),
    }


# ============================================================
# 品質チェック
# ============================================================

def quality_check(records: list[dict]) -> dict:
    """正規化結果の品質チェックレポートを出力"""
    total = len(records)
    print(f"\n{'=' * 60}")
    print(f"  品質チェック（{total:,}件）")
    print(f"{'=' * 60}")

    checks = {
        "office_id": lambda r: r.get("office_id") not in (None, ""),
        "name": lambda r: r.get("name") is not None,
        "prefecture": lambda r: r.get("prefecture") is not None,
        "pref_code": lambda r: r.get("pref_code") not in (None, ""),
        "city": lambda r: r.get("city") is not None,
        "city_code": lambda r: r.get("city_code") not in (None, ""),
        "address": lambda r: r.get("address") is not None,
        "tel": lambda r: r.get("tel") is not None,
        "fax": lambda r: r.get("fax") is not None,
        "latitude": lambda r: r.get("latitude") is not None,
        "longitude": lambda r: r.get("longitude") is not None,
        "corporation_number": lambda r: r.get("corporation_number") is not None,
        "corporation_name": lambda r: r.get("corporation_name") is not None,
        "website_url": lambda r: r.get("website_url") is not None,
        "office_code": lambda r: r.get("office_code") not in (None, ""),
        "business_days_text": lambda r: r.get("business_days_text") is not None,
        "capacity": lambda r: r.get("capacity") is not None,
    }

    stats = {}
    for field, check_fn in checks.items():
        count = sum(1 for r in records if check_fn(r))
        rate = count / total * 100 if total > 0 else 0
        mark = "OK  " if rate >= 95 else "LOW " if rate >= 50 else "WARN"
        print(f"  [{mark}] {field:25s}: {count:>6,}/{total:,} ({rate:5.1f}%)")
        stats[field] = {"count": count, "rate": round(rate, 1)}

    # office_id 重複チェック
    ids = [r["office_id"] for r in records]
    dup_count = len(ids) - len(set(ids))
    mark = "OK  " if dup_count == 0 else "WARN"
    print(f"\n  [{mark}] office_id重複: {dup_count}件")

    # 都道府県数チェック
    prefs = set(r["prefecture"] for r in records if r.get("prefecture"))
    mark = "OK  " if len(prefs) == 47 else "WARN"
    print(f"  [{mark}] 都道府県数: {len(prefs)}")

    # 都道府県別件数（上位10）
    from collections import Counter
    pref_counts = Counter(r["prefecture"] for r in records if r.get("prefecture"))
    print(f"\n  都道府県別（上位10）:")
    for pref, cnt in pref_counts.most_common(10):
        print(f"    {pref}: {cnt:,}件")

    print(f"{'=' * 60}")
    stats["_dup_office_id"] = dup_count
    stats["_pref_count"] = len(prefs)
    return stats


# ============================================================
# エントリポイント
# ============================================================

def main():
    input_path = INPUT_PATH
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"[ERROR] 入力ファイルが見つかりません: {input_path}")
        print(f"  scripts/download_csv.py を先に実行してください")
        sys.exit(1)

    records = normalize_all(input_path)
    write_outputs(records)
    quality_check(records)

    print(f"\n[normalize] 完了")


if __name__ == "__main__":
    main()
