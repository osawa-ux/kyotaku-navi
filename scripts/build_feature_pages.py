"""
代理指標フィルタ × 都道府県の静的フィーチャーページ生成スクリプト（Phase 2 量産用）

URL構造: /feature/{pref_slug}-{filter_key}.html
例: /feature/kanagawa-terminal_care_addon.html

Phase 1: 神奈川 × ターミナルケア対応 の 1 ページのみ生成
Phase 2: 全都道府県 × 4 フィルタ = 最大 188 ページ（データのある組み合わせのみ）

使用方法:
  python scripts/build_feature_pages.py --phase 1    # Phase 1: 神奈川のみ
  python scripts/build_feature_pages.py --phase 2    # Phase 2: 全都道府県 × 4フィルタ
  python scripts/build_feature_pages.py --pref kanagawa --filter terminal_care_addon
"""

import json
import sys
import os
import argparse
from datetime import date
from pathlib import Path
from html import escape as _html_escape
from urllib.parse import quote
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / 'config' / 'site_config.json'
DATA_FILE = BASE_DIR / 'data' / 'normalized' / 'offices_430.json'
DIST_DIR = BASE_DIR / 'dist'

with open(CONFIG_PATH, encoding='utf-8') as f:
    CFG = json.load(f)

SITE_URL = CFG.get('site_url', 'https://care.zaitaku-navi.com')
SITE_NAME = CFG.get('site_name', '居宅介護支援ナビ')
GA4_ID = CFG.get('analytics', {}).get('ga4_id', '')
DIFF_FILTERS_CFG = CFG.get('differentiator_filters', {}).get('filters', {})
ATTRIBUTION = CFG.get('attribution', {}).get('source', '')
CURRENT_YEAR = date.today().year

# 都道府県スラッグマップ
PREF_SLUG = {
    '01': 'hokkaido', '02': 'aomori', '03': 'iwate', '04': 'miyagi', '05': 'akita',
    '06': 'yamagata', '07': 'fukushima', '08': 'ibaraki', '09': 'tochigi', '10': 'gunma',
    '11': 'saitama', '12': 'chiba', '13': 'tokyo', '14': 'kanagawa', '15': 'niigata',
    '16': 'toyama', '17': 'ishikawa', '18': 'fukui', '19': 'yamanashi', '20': 'nagano',
    '21': 'gifu', '22': 'shizuoka', '23': 'aichi', '24': 'mie', '25': 'shiga',
    '26': 'kyoto', '27': 'osaka', '28': 'hyogo', '29': 'nara', '30': 'wakayama',
    '31': 'tottori', '32': 'shimane', '33': 'okayama', '34': 'hiroshima', '35': 'yamaguchi',
    '36': 'tokushima', '37': 'kagawa', '38': 'ehime', '39': 'kochi', '40': 'fukuoka',
    '41': 'saga', '42': 'nagasaki', '43': 'kumamoto', '44': 'oita', '45': 'miyazaki',
    '46': 'kagoshima', '47': 'okinawa',
}

SLUG_TO_PREF_CODE = {v: k for k, v in PREF_SLUG.items()}


def h(s):
    if s is None:
        return ''
    return _html_escape(str(s))


def office_slug(office_id: str) -> str:
    return office_id.replace(':', '_')


def detail_url(o: dict) -> str:
    slug = office_slug(o['office_id'])
    return f'/caremanager/{slug}.html'


def city_slug(city_name: str) -> str:
    return quote(city_name, safe='')


def get_ga4_tag() -> str:
    if not GA4_ID:
        return ''
    return f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{GA4_ID}');</script>'''


def build_feature_page(pref_slug_val: str, filter_key: str, all_offices: list) -> tuple[str, int]:
    """
    1つのフィーチャーページHTMLを生成する。
    Returns: (html_string, office_count)
    """
    pref_code = SLUG_TO_PREF_CODE.get(pref_slug_val)
    if not pref_code:
        raise ValueError(f'Unknown pref slug: {pref_slug_val}')

    fcfg = DIFF_FILTERS_CFG.get(filter_key, {})
    filter_label = fcfg.get('label', filter_key)
    filter_desc = fcfg.get('description', '')

    # 対象事業所を抽出（都道府県 × フィルタ True のもの）
    pref_offices = [o for o in all_offices if o.get('pref_code') == pref_code]
    pref_name = pref_offices[0].get('prefecture', '') if pref_offices else ''

    # フィルタ適用（nullは除外、Trueのみ）
    if filter_key == 'chief_caremanager_count':
        filtered = [o for o in pref_offices if isinstance(o.get(filter_key), int) and o[filter_key] > 0]
    else:
        filtered = [o for o in pref_offices if o.get(filter_key) is True]

    count = len(filtered)

    # データがない場合は生成しない
    if count == 0:
        return None, 0

    # 市区町村別リスト
    by_city = defaultdict(list)
    for o in filtered:
        city = o.get('city', 'その他') or 'その他'
        by_city[city].append(o)

    city_links = '\n'.join(
        f'<a href="/pref/{pref_slug_val}/{city_slug(c)}.html" class="city-link">{h(c)} ({len(offs)})</a>'
        for c, offs in sorted(by_city.items(), key=lambda x: -len(x[1]))
    )

    # 事業所カード
    cards_html = ''
    for o in sorted(filtered, key=lambda x: (x.get('city', ''), x.get('name', ''))):
        cards_html += f'''<div class="card">
  <h3><a href="{detail_url(o)}">{h(o.get("name"))}</a></h3>
  <div class="meta">
    <span>{h(o.get("city"))}</span>
    <span>{h(o.get("address"))}</span><br>
    {f'<span>TEL: {h(o.get("tel"))}</span>' if o.get("tel") else ''}
    {f'<span>{h(o.get("corporation_name"))}</span>' if o.get("corporation_name") else ''}
  </div>
  <div class="badge-row"><span class="badge badge-terminal">{h(filter_label)}</span></div>
</div>
'''

    # 関連フィルタリンク
    related_links = ''
    for fk, fcfg2 in DIFF_FILTERS_CFG.items():
        if fk == filter_key or not fcfg2.get('enabled', True):
            continue
        fl = fcfg2.get('label', fk)
        related_links += f'<li><a href="/feature/{pref_slug_val}-{fk}.html" style="padding:4px 10px;background:#e8f5e9;border-radius:4px;font-size:0.9em">{h(pref_name)} × {h(fl)}</a></li>\n'

    # ページHTML構築
    ga4_tag = get_ga4_tag()
    canonical = f'{SITE_URL}/feature/{pref_slug_val}-{filter_key}.html'
    title = f'{pref_name}の{filter_label}ケアマネ事業所（{count}件）| {SITE_NAME}'
    desc = f'{pref_name}で{filter_label}の居宅介護支援事業所を{count}件掲載。公表データに基づく代理指標です。'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{h(title)}</title>
  <meta name="description" content="{h(desc)}">
  <link rel="canonical" href="{h(canonical)}">
  <meta property="og:title" content="{h(title)}">
  <meta property="og:description" content="{h(desc)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{h(canonical)}">
  <meta property="og:locale" content="ja_JP">
  <link rel="stylesheet" href="/static/style.css">
  {ga4_tag}
</head>
<body>
<header>
  <div class="header-inner">
    <div>
      <a href="/" class="site-title">{h(SITE_NAME)}</a>
      <div class="site-subtitle">全国の居宅介護支援事業所を検索</div>
    </div>
    <nav>
      <a href="/about.html">運営者情報</a>
    </nav>
  </div>
</header>

<nav class="breadcrumb">
  <a href="/">トップ</a> &gt;
  <a href="/pref/{pref_slug_val}.html">{h(pref_name)}</a> &gt;
  <span>{h(filter_label)}対応</span>
</nav>

<div class="container">
  <h1>{h(pref_name)}の{h(filter_label)}ケアマネ事業所</h1>

  <div style="background:#fff3e0;border:1px solid #ffe0b2;border-radius:8px;padding:14px 16px;margin:16px 0;font-size:0.9em">
    <strong>このページについて</strong><br>
    掲載情報は<a href="https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html" target="_blank" rel="noopener">介護サービス情報公表システム（厚生労働省）</a>の公表データに基づく代理指標です。
    {h(filter_label)}の算定実績は事業所の体制・経験の<strong>参考情報</strong>であり、医療依存度の確定的な判定や特定の疾患・状態への対応を保証するものではありません。
    必ず直接事業所にご確認ください。
  </div>

  <p style="margin:8px 0;color:#444;font-size:0.9em">{h(filter_desc)}</p>

  <div class="stats-bar">
    <div class="stat-box"><div class="num">{count}</div><div class="label">{h(filter_label)}対応事業所</div></div>
    <div class="stat-box"><div class="num">{len(by_city)}</div><div class="label">市区町村</div></div>
  </div>

  <h2 style="margin-top:24px;font-size:1.1em">市区町村から探す</h2>
  <div class="city-grid">
    {city_links}
  </div>

  <h2 style="margin-top:24px;font-size:1.1em">{h(pref_name)}の{h(filter_label)}ケアマネ事業所一覧（{count}件）</h2>
  <div class="card-grid">
    {cards_html}
  </div>

  <div style="margin-top:32px;padding-top:16px;border-top:1px solid #e0e0e0">
    <h3 style="font-size:1em;margin-bottom:8px">他の特性で探す</h3>
    <ul style="list-style:none;display:flex;flex-wrap:wrap;gap:8px">
      {related_links}
    </ul>
  </div>

  <p style="margin-top:16px"><a href="/pref/{pref_slug_val}.html">&larr; {h(pref_name)}の全ケアマネ事業所一覧</a></p>

  <p style="margin-top:8px;font-size:0.75em;color:#aaa">
    データ出典: {h(ATTRIBUTION)}
  </p>
</div>

<footer>
  <div class="footer-inner">
    <p><strong>{h(SITE_NAME)}</strong></p>
    <div class="footer-bottom">&copy; {CURRENT_YEAR} {h(SITE_NAME)}</div>
  </div>
</footer>
</body>
</html>
"""
    return html, count


def main():
    parser = argparse.ArgumentParser(description='代理指標フィーチャーページ生成')
    parser.add_argument('--phase', type=int, choices=[1, 2], default=1,
                        help='Phase 1: 神奈川のみ / Phase 2: 全都道府県×全フィルタ')
    parser.add_argument('--pref', type=str, default=None,
                        help='都道府県スラッグ（例: kanagawa）')
    parser.add_argument('--filter', type=str, default=None, dest='filter_key',
                        help='フィルタキー（例: terminal_care_addon）')
    parser.add_argument('--demo', action='store_true',
                        help='データがない場合もサンプルページを生成（Phase 1 確認用）')
    args = parser.parse_args()

    # データ読み込み
    print(f'データ読込: {DATA_FILE}')
    with open(DATA_FILE, encoding='utf-8') as f:
        all_offices = json.load(f)
    print(f'  {len(all_offices):,}件')

    # 出力ディレクトリ
    # --demo フラグ時はデモファイルを _demo/feature/ に隔離（本番 dist/ へ混入しない）
    if args.demo:
        feature_dir = DIST_DIR / '_demo' / 'feature'
    else:
        feature_dir = DIST_DIR / 'feature'
    feature_dir.mkdir(parents=True, exist_ok=True)

    # ターゲット決定
    if args.pref and args.filter_key:
        targets = [(args.pref, args.filter_key)]
    elif args.phase == 1:
        targets = [('kanagawa', 'terminal_care_addon')]
    else:  # Phase 2
        targets = [
            (pref_slug, fk)
            for pref_slug in PREF_SLUG.values()
            for fk in DIFF_FILTERS_CFG.keys()
            if DIFF_FILTERS_CFG[fk].get('enabled', True)
        ]

    generated = 0
    skipped = 0
    results = []

    for pref_slug_val, filter_key in targets:
        try:
            # --demo モード: データなし時はデモ用に一部事業所をサンプルとして扱う
            if args.demo and args.phase == 1:
                demo_offices = []
                pref_code = SLUG_TO_PREF_CODE.get(pref_slug_val, '')
                sample = [o for o in all_offices if o.get('pref_code') == pref_code][:20]
                for o in sample:
                    demo_o = dict(o)
                    demo_o[filter_key] = True  # デモ用に強制True
                    demo_offices.append(demo_o)
                html, count = build_feature_page(pref_slug_val, filter_key, demo_offices + [o for o in all_offices if o.get('pref_code') != pref_code])
                if html:
                    results.append(f'  DEMO  {pref_slug_val} × {filter_key}: {count}件（デモデータ）')
            else:
                html, count = build_feature_page(pref_slug_val, filter_key, all_offices)
            if html is None:
                skipped += 1
                results.append(f'  SKIP  {pref_slug_val} × {filter_key} (データなし)')
                continue

            out_path = feature_dir / f'{pref_slug_val}-{filter_key}.html'
            out_path.write_text(html, encoding='utf-8')
            generated += 1
            results.append(f'  OK    {pref_slug_val} × {filter_key}: {count}件 → {out_path.name}')
        except Exception as e:
            results.append(f'  ERROR {pref_slug_val} × {filter_key}: {e}')

    print('\n'.join(results))
    print(f'\n生成完了: {generated}ページ / スキップ: {skipped}（データなし）')

    if generated > 0:
        print(f'\nPre-Build Validation:')
        print(f'  総件数: {len(all_offices):,}件（変更なし）')
        print(f'  フィーチャーページ: {generated}ページ')
        print(f'  出力先: {feature_dir}')


if __name__ == '__main__':
    main()
