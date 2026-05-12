"""
kaigokensaku.mhlw.go.jp 介護サービス情報公表システム 詳細ページ収集スクリプト

## 倫理・利用規約方針

robots.txt 確認結果 (2026-05-12 時点):
  - Disallow: /shuukei /kanri /houkoku /seikatu_kanri /err /upload
  - 事業所詳細ページ (/NN/index.php?action_kouhyou_detail_*) は Disallow 対象外

サイト利用規約 (https://www.kaigokensaku.mhlw.go.jp/copyright/) 抜粋:
  - 転載を行う場合は出所を明記してください
  - 「本ウェブサイトの目的に沿って利用することとし、関係のない営利行為等の対象に
    する行為については、これを禁止します」

本スクリプトの利用目的の解釈:
  - 取得するのは公表済み介護事業所情報の公的データ
  - 厚労省オープンデータ CSV (CC BY 4.0) の補完として、同一データソースの詳細属性を取得
  - 在宅クリニックナビは患者・家族向けの情報提供サービスであり、ケアマネ選択支援が目的
  - 「介護サービス情報公表システム」の公表目的（利用者へのサービス情報提供）と合致する
  - 出所は明記する (care.zaitaku-navi.com のデータ出典表示)

注意: 「関係のない営利行為等」の解釈は運営者判断の余地がある。
  本スクリプトは識別可能な User-Agent を使い、サイト負荷を最小化する設計とする。
  問題があった場合は即停止できる設計 (進捗ファイル + skip 機能)。

## rate limit 方針
  - 1 req / 2-3 秒 (公的サイト負荷配慮)
  - 10 件ごとに 5 秒の追加休止
  - セッション確立 (都道府県ページ経由) → 詳細ページアクセス

## セッション管理
  kaigokensaku は PHP セッションを使用。
  直接詳細ページへのアクセスはエラーになる。
  フロー: トップ → 都道府県トップ → 検索一覧 (POST) → JSON API → 詳細ページ (GET)
  都道府県ごとにセッションを確立し、VersionCd を取得してから詳細ページを叩く。

## 取得属性
  - terminal_care_addon (bool): ターミナルケアマネジメント加算 あり/なし
  - specific_office_addon (bool): 特定事業所加算 I/II/III/A のいずれかに該当
  - emergency_phone_support (bool): 緊急時の電話連絡の対応状況 あり/なし
  - chief_caremanager_count (int): うち主任介護支援専門員数（常勤+非常勤の合計）

## 実行方法
  # dry-run (5件のみ取得)
  python scripts/download_kaigokensaku.py --dry-run

  # 全件取得 (36,491件、数日かかる)
  python scripts/download_kaigokensaku.py

  # 途中から再開
  python scripts/download_kaigokensaku.py  # 既存ファイルは自動スキップ

  # 都道府県を限定
  python scripts/download_kaigokensaku.py --pref 14

  # 属性 JSON の集計 (取得済みファイルから再集計)
  python scripts/download_kaigokensaku.py --aggregate-only
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ============================================================
# 定数・パス設定
# ============================================================

BASE_DIR = Path(__file__).parent.parent
INPUT_JSON = BASE_DIR / "data" / "normalized" / "offices_430.json"
OUTPUT_DETAILS_DIR = BASE_DIR / "data" / "kaigokensaku" / "details"
OUTPUT_ATTRS_JSON = BASE_DIR / "data" / "kaigokensaku" / "attributes.json"
PROGRESS_FILE = BASE_DIR / "data" / "kaigokensaku" / ".progress.json"

BASE_URL = "https://www.kaigokensaku.mhlw.go.jp"
SERVICE_CODE = "430"

# --- rate limit 設定 ---
# 1 req あたりの最小/最大待機秒数 (random.uniform で決定)
RATE_LIMIT_MIN = 2.0
RATE_LIMIT_MAX = 3.5
# N 件ごとに追加休止
BATCH_SIZE = 10
BATCH_PAUSE = 5.0
# HTTP エラー時の retry 設定
MAX_RETRY = 3
RETRY_WAIT = 10.0

# --- User-Agent 設定の注意 ---
# 独自 UA (zaitaku-navi-data-collector) を使用すると kaigokensaku の JSON API が
# Bot 検出により「エラーが発生しました」を返すことが dry-run 時に確認された。
# そのため標準的なブラウザ UA を使用する。
# 倫理的透明性のため、連絡先をリクエストヘッダー (X-Contact) に別途付与する。
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
# 連絡先ヘッダー: 問い合わせ窓口を明示する
CONTACT_HEADER = "osawa@yokohama-home.jp (zaitaku-navi public data collection)"

JST = timezone(timedelta(hours=9))

# ============================================================
# ロギング設定
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ============================================================
# セッション管理
# ============================================================

class KaigoKensakuSession:
    """
    kaigokensaku のセッション管理クラス。
    都道府県ごとにセッションを確立し、VersionCd を取得する。
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
            "Accept-Encoding": "identity",  # gzip は Python 側でデコード不要のため無効
            "X-Contact": CONTACT_HEADER,    # 問い合わせ窓口の透明性確保
        })
        self._current_pref = None
        self._version_cd_cache: dict[str, str] = {}  # pref_code -> version_cd

    def _sleep(self, min_sec: float = RATE_LIMIT_MIN, max_sec: float = RATE_LIMIT_MAX):
        """rate limit 用スリープ"""
        t = random.uniform(min_sec, max_sec)
        time.sleep(t)

    def establish_session(self, pref_code: str) -> Optional[str]:
        """
        指定都道府県のセッションを確立し、VersionCd を返す。
        エラー時は None を返す。

        セッション確立フロー:
          Step 1: 全国版トップ (PHPSESSID 取得)
          Step 2: 都道府県トップ (_c_[pref] クッキー取得)
          Step 3: 検索ページ (action_kouhyou_pref_topjigyosyo_index)
          Step 4: 検索結果ページ POST (URL に action を含める)
          Step 5: JSON API で VersionCd 取得

        注意事項:
          - _sp_ クッキーを手動設定すると逆に JSON API がエラーになる (実験確認済み)
          - Step 4 の POST URL は ?action_kouhyou_pref_search_list_list=true をURLに含める
          - SearchConditions JSON フィールドは不要
          - _sp_ がなくても正常に JSON API が成功することを実機確認済み
        """
        if pref_code in self._version_cd_cache:
            return self._version_cd_cache[pref_code]

        logger.info(f"[session] pref_code={pref_code} のセッション確立開始")

        try:
            # Step 1: 全国版トップ
            r0 = self.session.get(f"{BASE_URL}/", timeout=30)
            r0.raise_for_status()
            self._sleep(1.0, 2.0)

            # Step 2: 都道府県トップ
            r1 = self.session.get(
                f"{BASE_URL}/{pref_code}/index.php",
                headers={"Referer": f"{BASE_URL}/"},
                timeout=30,
            )
            r1.raise_for_status()
            self._sleep(1.0, 2.0)

            # Step 3: 検索ページ
            r2 = self.session.get(
                f"{BASE_URL}/{pref_code}/index.php",
                params={"action_kouhyou_pref_topjigyosyo_index": "true"},
                headers={"Referer": f"{BASE_URL}/{pref_code}/index.php"},
                timeout=30,
            )
            r2.raise_for_status()
            self._sleep(1.0, 2.0)

            # Step 4: 検索結果ページ (POST)
            # URL に action を直接含める (params= では動作しない)
            # _sp_ クッキーは設定しない (設定すると JSON API がエラーになる)
            r3 = self.session.post(
                f"{BASE_URL}/{pref_code}/index.php?action_kouhyou_pref_search_list_list=true",
                data={
                    "action_kouhyou_pref_topjigyosyo_index": "true",
                    "method": "search",
                    "PrefCd": pref_code,
                    "ServiceCd": SERVICE_CODE,
                    "Shikuchoson": "",
                    "FromPage": "kaigoTopPage",
                },
                headers={
                    "Referer": f"{BASE_URL}/{pref_code}/index.php?action_kouhyou_pref_topjigyosyo_index=true",
                },
                timeout=30,
            )
            r3.raise_for_status()
            self._sleep(1.0, 2.0)

            # Step 5: JSON API で事業所リストを取得 → VersionCd 確認
            r_json = self.session.get(
                f"{BASE_URL}/{pref_code}/index.php",
                params={
                    "action_kouhyou_pref_search_search": "true",
                    "method": "search",
                    "p_count": "5",
                    "p_offset": "0",
                    "p_sort_name": "FreeNumUpdateDate",
                    "p_order": "1",
                },
                headers={
                    "Referer": f"{BASE_URL}/{pref_code}/index.php?action_kouhyou_pref_search_list_list=true",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=30,
            )
            r_json.raise_for_status()

            result = r_json.json()
            if result.get("status") != "success" or not isinstance(result.get("data"), list):
                logger.warning(f"[session] pref={pref_code} JSON API エラー: {result.get('data', 'unknown')}")
                return None

            # VersionCd を取得
            version_cd = result["data"][0].get("VersionCd", "023")
            self._version_cd_cache[pref_code] = version_cd
            self._current_pref = pref_code
            logger.info(f"[session] pref_code={pref_code} セッション確立完了, VersionCd={version_cd}")
            return version_cd

        except Exception as e:
            logger.error(f"[session] pref_code={pref_code} セッション確立失敗: {e}")
            return None

    def fetch_detail_page(self, pref_code: str, office_code: str, sub_cd: str = "00") -> Optional[str]:
        """
        事業所詳細ページ (kihon タブ) の HTML を取得する。
        セッションがなければ確立してから取得する。
        エラー時は None を返す。
        """
        version_cd = self.establish_session(pref_code)
        if version_cd is None:
            return None

        jigyosyo_cd_full = f"{office_code}-{sub_cd}"
        url = (
            f"{BASE_URL}/{pref_code}/index.php"
            f"?action_kouhyou_detail_{version_cd}_kihon=true"
            f"&JigyosyoCd={jigyosyo_cd_full}&ServiceCd={SERVICE_CODE}"
        )
        referer = (
            f"{BASE_URL}/{pref_code}/index.php"
            f"?action_kouhyou_detail_{version_cd}_kani=true"
            f"&JigyosyoCd={jigyosyo_cd_full}&ServiceCd={SERVICE_CODE}"
        )

        for attempt in range(1, MAX_RETRY + 1):
            try:
                r = self.session.get(
                    url,
                    headers={"Referer": referer},
                    timeout=60,
                )
                if r.status_code == 200:
                    text = r.content.decode("utf-8", errors="replace")
                    # エラーページ検出
                    if "エラーが発生しました" in text and len(text) < 10000:
                        logger.warning(
                            f"[fetch] エラーページ返却: pref={pref_code}, office={office_code}"
                            f" -> セッション再確立"
                        )
                        # セッションをリセットして再確立
                        del self._version_cd_cache[pref_code]
                        version_cd = self.establish_session(pref_code)
                        if version_cd is None:
                            return None
                        # URL を更新して retry
                        url = (
                            f"{BASE_URL}/{pref_code}/index.php"
                            f"?action_kouhyou_detail_{version_cd}_kihon=true"
                            f"&JigyosyoCd={jigyosyo_cd_full}&ServiceCd={SERVICE_CODE}"
                        )
                        referer = (
                            f"{BASE_URL}/{pref_code}/index.php"
                            f"?action_kouhyou_detail_{version_cd}_kani=true"
                            f"&JigyosyoCd={jigyosyo_cd_full}&ServiceCd={SERVICE_CODE}"
                        )
                        self._sleep(RETRY_WAIT, RETRY_WAIT + 5)
                        continue
                    return text
                elif r.status_code in (429, 503):
                    # レートリミット / サービス不可 -> 長めに待つ
                    wait = RETRY_WAIT * attempt
                    logger.warning(f"[fetch] HTTP {r.status_code} -> {wait}秒後 retry ({attempt}/{MAX_RETRY})")
                    time.sleep(wait)
                elif r.status_code in (400, 403, 404):
                    logger.warning(f"[fetch] HTTP {r.status_code}: pref={pref_code}, office={office_code}")
                    return None
                else:
                    logger.warning(f"[fetch] HTTP {r.status_code} -> retry ({attempt}/{MAX_RETRY})")
                    time.sleep(RETRY_WAIT)
            except requests.RequestException as e:
                logger.warning(f"[fetch] 例外 ({attempt}/{MAX_RETRY}): {e}")
                time.sleep(RETRY_WAIT)

        logger.error(f"[fetch] 全 retry 失敗: pref={pref_code}, office={office_code}")
        return None


# ============================================================
# HTML 解析 - 4 属性の抽出
# ============================================================

# abbr 属性での候補 (表記揺れを考慮した複数候補)
_TERMINAL_CARE_ABBR = [
    "ターミナルケアマネジメント加算",
]
_SPECIFIC_OFFICE_ABBR = [
    "特定事業所加算（Ⅰ）",
    "特定事業所加算（Ⅱ）",
    "特定事業所加算（Ⅲ）",
    "特定事業所加算（A）",
    # 旧表記
    "特定事業所加算（I）",
    "特定事業所加算（II）",
    "特定事業所加算（III）",
]
_EMERGENCY_PHONE_ABBR = [
    "緊急時の電話連絡の対応状況",
    "緊急時の電話対応の有無",  # kani ページ表記
    "緊急時の電話連絡対応",
]
_CHIEF_CM_ABBR = [
    "うち主任介護支援専門員",
    "うち主任ケアマネジャー数",
    "主任介護支援専門員数",
]


def _is_ari(td_tag) -> bool:
    """<td> の中に ico_jigyosho_ari.gif があれば True"""
    if td_tag is None:
        return False
    img = td_tag.find("img")
    if img:
        alt = img.get("alt", "")
        src = img.get("src", "")
        if alt == "あり" or "ico_jigyosho_ari" in src:
            return True
        if alt == "なし" or "ico_jigyosho_nashi" in src:
            return False
    # テキストで判定
    text = td_tag.get_text(strip=True)
    if "あり" in text:
        return True
    return False


def _parse_count(td_tag) -> Optional[int]:
    """<td> のテキストから「N人」の数値を取得する。失敗は None"""
    if td_tag is None:
        return None
    text = td_tag.get_text(strip=True)
    # 「1人」「0人」などにマッチ
    m = re.search(r"(\d+)\s*人", text)
    if m:
        return int(m.group(1))
    # 数字のみの場合も対応
    m2 = re.search(r"^\s*(\d+)\s*$", text)
    if m2:
        return int(m2.group(1))
    return None


def _find_next_td(soup: BeautifulSoup, abbr_candidates: list[str]):
    """
    abbr 属性が candidates のいずれかにマッチする <th> の次の <td> を返す。
    見つからなければ None。
    """
    for abbr in abbr_candidates:
        th = soup.find("th", attrs={"abbr": abbr})
        if th:
            # <th> の次の兄弟要素で最初の <td>
            td = th.find_next_sibling("td")
            if td:
                return td
    return None


def _extract_chief_caremanager_count(soup: BeautifulSoup) -> Optional[int]:
    """
    「うち主任介護支援専門員」行を探し、常勤 + 非常勤の合計を返す。
    複数の <td> が続く場合は最初の数値 <td> を常勤、2番目を非常勤として合算する。
    見つからない場合は None。
    """
    for abbr in _CHIEF_CM_ABBR:
        th = soup.find("th", attrs={"abbr": abbr})
        if th:
            # この <th> の同一 <tr> 内、または次の兄弟 <td> を収集
            tds = th.find_next_siblings("td")
            if not tds:
                # <th> が rowspan で跨いでいる場合は親 <tr> の次の行の <td> を探す
                tr = th.find_parent("tr")
                if tr:
                    next_tr = tr.find_next_sibling("tr")
                    if next_tr:
                        tds = next_tr.find_all("td")

            counts = []
            for td in tds[:3]:  # 常勤/非常勤/合計 の最大3セル
                n = _parse_count(td)
                if n is not None:
                    counts.append(n)

            if counts:
                # 常勤 + 非常勤の合計 (最初の2値を合算。1値のみなら単独)
                if len(counts) >= 2:
                    return counts[0] + counts[1]
                return counts[0]
    return None


def extract_attributes(html: str, office_code: str) -> dict:
    """
    事業所詳細ページ (kihon) の HTML から 4 属性を抽出して返す。

    Returns:
        {
            "office_code": str,
            "terminal_care_addon": bool | None,
            "specific_office_addon": bool | None,
            "emergency_phone_support": bool | None,
            "chief_caremanager_count": int | None,
            "parse_ok": bool,        # 解析が部分的にでも成功したか
            "sanity_ok": bool,       # 構造 sanity check OK か
            "extracted_at": str,
        }
    """
    result = {
        "office_code": office_code,
        "terminal_care_addon": None,
        "specific_office_addon": None,
        "emergency_phone_support": None,
        "chief_caremanager_count": None,
        "parse_ok": False,
        "sanity_ok": False,
        "extracted_at": datetime.now(JST).isoformat(),
    }

    if not html:
        return result

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        logger.error(f"[parse] BeautifulSoup 失敗: {office_code}: {e}")
        return result

    # --- sanity check: 期待するページか確認 ---
    title = soup.find("title")
    title_text = title.get_text() if title else ""
    # 「事業所の詳細」または「居宅介護支援」が含まれていれば正しいページ
    sanity_ok = "事業所の詳細" in title_text or "居宅介護支援" in title_text
    result["sanity_ok"] = sanity_ok

    if not sanity_ok:
        logger.warning(f"[parse] sanity check 失敗: {office_code}, title={title_text[:80]}")
        # sanity 失敗でも可能な限り解析を試みる
        if "エラー" in title_text:
            return result

    # --- 1. ターミナルケアマネジメント加算 ---
    td_terminal = _find_next_td(soup, _TERMINAL_CARE_ABBR)
    if td_terminal is not None:
        result["terminal_care_addon"] = _is_ari(td_terminal)

    # --- 2. 特定事業所加算 (I/II/III/A のいずれかが「あり」で True) ---
    specific_addon = False
    specific_found = False
    for abbr in _SPECIFIC_OFFICE_ABBR:
        th = soup.find("th", attrs={"abbr": abbr})
        if th:
            specific_found = True
            td = th.find_next_sibling("td")
            if td and _is_ari(td):
                specific_addon = True
                break  # 一つでも「あり」があれば True
    if specific_found:
        result["specific_office_addon"] = specific_addon

    # --- 3. 緊急時電話連絡 ---
    td_emergency = _find_next_td(soup, _EMERGENCY_PHONE_ABBR)
    if td_emergency is not None:
        result["emergency_phone_support"] = _is_ari(td_emergency)

    # --- 4. 主任介護支援専門員配置数 ---
    result["chief_caremanager_count"] = _extract_chief_caremanager_count(soup)

    # 少なくとも1属性が取得できていれば parse_ok = True
    result["parse_ok"] = any(
        result[k] is not None
        for k in ("terminal_care_addon", "specific_office_addon",
                  "emergency_phone_support", "chief_caremanager_count")
    )

    return result


# ============================================================
# 進捗管理
# ============================================================

def load_progress() -> dict:
    """進捗ファイルを読み込む。なければ空の進捗を返す。"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "started_at": datetime.now(JST).isoformat(),
        "total": 0,
        "done": 0,
        "skipped": 0,
        "errors": 0,
        "last_office_code": None,
    }


def save_progress(progress: dict):
    """進捗ファイルを保存する。"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now(JST).isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ============================================================
# 個別ファイル保存・読み込み
# ============================================================

def detail_file_path(office_code: str) -> Path:
    """office_code に対応する個別 JSON ファイルパスを返す"""
    return OUTPUT_DETAILS_DIR / f"{office_code}.json"


def is_already_done(office_code: str) -> bool:
    """既に取得済み (ファイルが存在) かどうか"""
    return detail_file_path(office_code).exists()


def save_detail(office_code: str, attrs: dict):
    """個別 JSON ファイルを保存する"""
    OUTPUT_DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    path = detail_file_path(office_code)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(attrs, f, ensure_ascii=False, indent=2)


# ============================================================
# 集計 - attributes.json の生成
# ============================================================

def aggregate_attributes() -> dict:
    """
    details/ ディレクトリの全 JSON ファイルを集計して attributes.json を生成する。

    Returns: office_code -> 4属性 の dict
    """
    if not OUTPUT_DETAILS_DIR.exists():
        logger.warning(f"[aggregate] details ディレクトリが存在しません: {OUTPUT_DETAILS_DIR}")
        return {}

    result = {}
    files = list(OUTPUT_DETAILS_DIR.glob("*.json"))
    logger.info(f"[aggregate] {len(files)} 件のファイルを集計中...")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            office_code = data.get("office_code") or f.stem
            result[office_code] = {
                "terminal_care_addon": data.get("terminal_care_addon"),
                "specific_office_addon": data.get("specific_office_addon"),
                "emergency_phone_support": data.get("emergency_phone_support"),
                "chief_caremanager_count": data.get("chief_caremanager_count"),
                "parse_ok": data.get("parse_ok", False),
                "sanity_ok": data.get("sanity_ok", False),
                "extracted_at": data.get("extracted_at"),
            }
        except Exception as e:
            logger.warning(f"[aggregate] ファイル読込エラー: {f}: {e}")

    # 集計統計
    total = len(result)
    parse_ok = sum(1 for v in result.values() if v.get("parse_ok"))
    sanity_ok = sum(1 for v in result.values() if v.get("sanity_ok"))
    terminal_true = sum(1 for v in result.values() if v.get("terminal_care_addon") is True)
    specific_true = sum(1 for v in result.values() if v.get("specific_office_addon") is True)
    emergency_true = sum(1 for v in result.values() if v.get("emergency_phone_support") is True)
    chief_not_null = sum(1 for v in result.values() if v.get("chief_caremanager_count") is not None)

    logger.info(f"[aggregate] 集計完了: {total} 件")
    logger.info(f"  parse_ok: {parse_ok}/{total}")
    logger.info(f"  sanity_ok: {sanity_ok}/{total}")
    logger.info(f"  terminal_care_addon=True: {terminal_true}")
    logger.info(f"  specific_office_addon=True: {specific_true}")
    logger.info(f"  emergency_phone_support=True: {emergency_true}")
    logger.info(f"  chief_caremanager_count 非null: {chief_not_null}")

    # attributes.json 保存
    OUTPUT_ATTRS_JSON.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "_meta": {
            "aggregated_at": datetime.now(JST).isoformat(),
            "total_offices": total,
            "parse_ok": parse_ok,
            "sanity_ok": sanity_ok,
        },
        "offices": result,
    }
    with open(OUTPUT_ATTRS_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"[aggregate] attributes.json 保存: {OUTPUT_ATTRS_JSON}")

    return result


# ============================================================
# メイン処理
# ============================================================

def load_offices(pref_filter: Optional[str] = None) -> list[dict]:
    """offices_430.json を読み込んで処理対象リストを返す"""
    if not INPUT_JSON.exists():
        logger.error(f"[main] 入力ファイルが見つかりません: {INPUT_JSON}")
        sys.exit(1)

    with open(INPUT_JSON, encoding="utf-8") as f:
        offices = json.load(f)

    if pref_filter:
        offices = [o for o in offices if o.get("pref_code") == pref_filter]
        logger.info(f"[main] 都道府県フィルタ pref_code={pref_filter}: {len(offices)} 件")

    return offices


def run(args):
    """メイン実行ロジック"""

    if args.aggregate_only:
        aggregate_attributes()
        return

    offices = load_offices(pref_filter=args.pref)
    total = len(offices)
    logger.info(f"[main] 処理対象: {total} 件")

    if args.dry_run:
        # dry-run: 5件のみ
        offices = offices[:5]
        logger.info(f"[main] dry-run モード: {len(offices)} 件のみ実行")

    progress = load_progress()
    progress["total"] = total

    session = KaigoKensakuSession()
    done_count = 0
    error_count = 0
    skip_count = 0

    for i, office in enumerate(offices, 1):
        office_code = office.get("office_code", "")
        pref_code = office.get("pref_code", "")
        name = office.get("name") or "?"

        if not office_code or not pref_code:
            logger.warning(f"[main] office_code または pref_code が空: idx={i}")
            error_count += 1
            continue

        # 既存ファイルがあれば skip
        if not args.dry_run and is_already_done(office_code):
            skip_count += 1
            if skip_count % 1000 == 0:
                logger.info(f"[main] skip {skip_count} 件目... (直近: {office_code})")
            continue

        logger.info(f"[main] ({i}/{total}) pref={pref_code}, office={office_code}, name={name}")

        # HTML 取得
        html = session.fetch_detail_page(pref_code, office_code)

        if html is None:
            logger.error(f"[main] HTML 取得失敗: {office_code}")
            # エラー記録 (失敗フラグ付きで保存)
            attrs = {
                "office_code": office_code,
                "terminal_care_addon": None,
                "specific_office_addon": None,
                "emergency_phone_support": None,
                "chief_caremanager_count": None,
                "parse_ok": False,
                "sanity_ok": False,
                "fetch_error": True,
                "extracted_at": datetime.now(JST).isoformat(),
            }
            save_detail(office_code, attrs)
            error_count += 1
        else:
            # HTML 解析
            attrs = extract_attributes(html, office_code)
            save_detail(office_code, attrs)

            if attrs["parse_ok"]:
                done_count += 1
                logger.info(
                    f"[main] 抽出成功: terminal={attrs['terminal_care_addon']}, "
                    f"specific={attrs['specific_office_addon']}, "
                    f"emergency={attrs['emergency_phone_support']}, "
                    f"chief={attrs['chief_caremanager_count']}"
                )
            else:
                logger.warning(f"[main] 属性抽出できず (parse_ok=False): {office_code}")
                error_count += 1

        # 進捗保存
        progress["done"] = done_count + skip_count
        progress["skipped"] = skip_count
        progress["errors"] = error_count
        progress["last_office_code"] = office_code
        save_progress(progress)

        # rate limit
        if i % BATCH_SIZE == 0:
            logger.info(f"[main] {i} 件処理完了 (done={done_count}, skip={skip_count}, err={error_count}) -> {BATCH_PAUSE}s pause")
            time.sleep(BATCH_PAUSE)
        else:
            session._sleep()

    # 最終集計
    logger.info(f"[main] 完了: done={done_count}, skip={skip_count}, error={error_count}")

    if not args.dry_run or skip_count + done_count > 0:
        aggregate_attributes()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="kaigokensaku 事業所詳細ページから 4 属性を取得する"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="5 件のみ取得して構造確認 (本格実行前の動作確認用)",
    )
    parser.add_argument(
        "--pref",
        type=str,
        default=None,
        help="都道府県コード (例: 14=神奈川県) で絞り込む",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="取得済みファイルから attributes.json のみ再集計する",
    )
    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
