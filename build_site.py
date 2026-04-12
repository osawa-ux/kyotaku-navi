"""
居宅介護支援事業所ナビ 静的サイト生成スクリプト

使用方法:
  python build_site.py              # サイト生成
  python build_site.py --preview    # 生成後にローカルサーバー起動

生成物:
  dist/
  ├── index.html                     # トップページ（都道府県一覧）
  ├── pref/{pref_slug}.html          # 都道府県ページ
  ├── pref/{pref_slug}/{city}.html   # 市区町村ページ
  ├── office/{slug}.html             # 事業所詳細ページ
  ├── data/
  │   ├── search/{pref_code}.json    # 都道府県別検索JSON
  │   └── offices_geo.json           # 地図用軽量JSON
  ├── sitemap.xml
  ├── robots.txt
  └── static/
      └── style.css

設計方針:
  訪問診療ナビ (MyPython/build_site.py) と同一パターンで構築。
  site_config.json で業種固有文言を切り替える config-driven 方式。
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from html import escape as _html_escape
from pathlib import Path
from urllib.parse import quote

sys.stdout.reconfigure(encoding='utf-8')

# =============================================================
# 設定読み込み
# =============================================================

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config' / 'site_config.json'

with open(CONFIG_PATH, encoding='utf-8') as f:
    CFG = json.load(f)

SITE_NAME = CFG['site_name']
SITE_DESC = CFG['site_description']
SITE_URL = CFG.get('site_url', '')
ENTITY_NAME = CFG.get('entity_name', '事業所')
ENTITY_TYPE = CFG.get('entity_type', '居宅介護支援事業所')
CARE_TYPE = CFG.get('care_type', '居宅介護支援')
ENTITY_DETAIL_PREFIX = CFG.get('entity_detail_prefix', 'office')
OPERATOR_NAME = 'MDX株式会社'
GA4_ID = CFG.get('analytics', {}).get('ga4_id', '')
ATTRIBUTION = CFG.get('attribution', {}).get('source', '')

DATA_FILE = BASE_DIR / 'data' / 'normalized' / 'offices_430.json'
DIST_DIR = BASE_DIR / CFG.get('build', {}).get('output_dir', 'dist')

# =============================================================
# 都道府県マスタ（訪問診療ナビと完全同一）
# =============================================================

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

PREF_CODE_TO_NAME = {
    '01': '北海道', '02': '青森県', '03': '岩手県', '04': '宮城県', '05': '秋田県',
    '06': '山形県', '07': '福島県', '08': '茨城県', '09': '栃木県', '10': '群馬県',
    '11': '埼玉県', '12': '千葉県', '13': '東京都', '14': '神奈川県', '15': '新潟県',
    '16': '富山県', '17': '石川県', '18': '福井県', '19': '山梨県', '20': '長野県',
    '21': '岐阜県', '22': '静岡県', '23': '愛知県', '24': '三重県', '25': '滋賀県',
    '26': '京都府', '27': '大阪府', '28': '兵庫県', '29': '奈良県', '30': '和歌山県',
    '31': '鳥取県', '32': '島根県', '33': '岡山県', '34': '広島県', '35': '山口県',
    '36': '徳島県', '37': '香川県', '38': '愛媛県', '39': '高知県', '40': '福岡県',
    '41': '佐賀県', '42': '長崎県', '43': '熊本県', '44': '大分県', '45': '宮崎県',
    '46': '鹿児島県', '47': '沖縄県',
}

REGIONS = [
    ('北海道・東北', ['01', '02', '03', '04', '05', '06', '07']),
    ('関東', ['08', '09', '10', '11', '12', '13', '14', '15']),
    ('中部', ['16', '17', '18', '19', '20', '21', '22', '23', '24']),
    ('近畿', ['25', '26', '27', '28', '29', '30']),
    ('中国・四国', ['31', '32', '33', '34', '35', '36', '37', '38', '39']),
    ('九州・沖縄', ['40', '41', '42', '43', '44', '45', '46', '47']),
]

# =============================================================
# ユーティリティ
# =============================================================

def h(s):
    """HTMLエスケープ"""
    if s is None:
        return ''
    return _html_escape(str(s))


def office_slug(office_id: str) -> str:
    """office_id からファイル名安全な slug を生成
    mhlw_kaigo:0170102313:430 → mhlw_kaigo_0170102313_430
    """
    return office_id.replace(':', '_')


def city_slug(city_name: str) -> str:
    """市区町村名からURL安全な slug を生成"""
    return quote(city_name, safe='')


# =============================================================
# CSS（訪問診療ナビと同系統のデザイン）
# =============================================================

COMMON_CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Hiragino Kaku Gothic ProN","Yu Gothic","Meiryo",sans-serif;color:#333;line-height:1.7;background:#f8f9fa}
a{color:#0066cc;text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:1000px;margin:0 auto;padding:20px 16px}

/* Header */
header{background:#1a6e3c;color:#fff;padding:12px 0}
header .header-inner{max-width:1000px;margin:0 auto;padding:0 16px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.site-title{color:#fff;font-size:1.3em;font-weight:bold;text-decoration:none}
.site-subtitle{color:rgba(255,255,255,0.85);font-size:0.8em}
header nav a{color:rgba(255,255,255,0.9);font-size:0.85em;margin-left:16px}

/* Breadcrumb */
.breadcrumb{font-size:0.85em;color:#666;margin:16px 0 8px;padding:0 16px;max-width:1000px;margin-left:auto;margin-right:auto}
.breadcrumb a{color:#0066cc}

/* Cards */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin:16px 0}
.card{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:16px;transition:box-shadow 0.2s}
.card:hover{box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.card h3{font-size:1em;margin-bottom:8px}
.card .meta{font-size:0.85em;color:#666;line-height:1.5}
.card .meta span{display:inline-block;margin-right:12px}

/* Region grid */
.region-section{margin:24px 0}
.region-section h3{font-size:1.05em;color:#1a6e3c;margin-bottom:8px;padding-bottom:4px;border-bottom:2px solid #e8f5e9}
.pref-grid{display:flex;flex-wrap:wrap;gap:6px}
.pref-link{display:inline-block;padding:6px 12px;background:#fff;border:1px solid #ddd;border-radius:4px;font-size:0.9em;white-space:nowrap}
.pref-link:hover{background:#e8f5e9;border-color:#1a6e3c;text-decoration:none}

/* City grid */
.city-grid{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.city-link{display:inline-block;padding:4px 10px;background:#fff;border:1px solid #ddd;border-radius:4px;font-size:0.85em}
.city-link:hover{background:#e8f5e9;text-decoration:none}

/* Detail page */
.detail-header{margin-bottom:24px}
.detail-header h1{font-size:1.4em;margin-bottom:4px}
.detail-header .kana{color:#888;font-size:0.85em}
.info-table{width:100%;border-collapse:collapse;margin:16px 0}
.info-table th{text-align:left;padding:10px 12px;background:#f5f5f5;border:1px solid #e0e0e0;width:140px;font-size:0.9em;color:#555;vertical-align:top}
.info-table td{padding:10px 12px;border:1px solid #e0e0e0;font-size:0.9em}
.map-container{margin:16px 0;border-radius:8px;overflow:hidden}

/* Stats */
.stats-bar{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}
.stat-box{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:12px 16px;text-align:center;min-width:120px}
.stat-box .num{font-size:1.6em;font-weight:bold;color:#1a6e3c}
.stat-box .label{font-size:0.8em;color:#888}

/* Footer */
footer{background:#333;color:#fff;padding:32px 0;margin-top:40px;font-size:0.85em}
footer .footer-inner{max-width:1000px;margin:0 auto;padding:0 16px}
footer a{color:#aed581}
.footer-pref-grid{display:flex;flex-wrap:wrap;gap:4px 8px;margin:8px 0}
.footer-pref-grid a{color:#aed581;font-size:0.8em}
.footer-bottom{margin-top:16px;padding-top:12px;border-top:1px solid #555;text-align:center;color:#999;font-size:0.8em}

/* Search box */
.search-box{margin:16px 0;padding:16px;background:#fff;border:1px solid #e0e0e0;border-radius:8px}
.search-box input[type=text]{width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:4px;font-size:1em}
.search-results{margin-top:12px}

/* Responsive */
@media(max-width:600px){
  .card-grid{grid-template-columns:1fr}
  header .header-inner{flex-direction:column;align-items:flex-start}
  .info-table th{width:100px}
}
"""

# =============================================================
# 検索JS（都道府県別JSON読み込み・フィルタリング）
# =============================================================

SEARCH_JS = """\
(function(){
  var input=document.getElementById('search-input');
  var results=document.getElementById('search-results');
  var data=[];
  var prefCode=document.body.dataset.prefCode||'';
  if(!prefCode||!input)return;
  fetch('/data/search/'+prefCode+'.json')
    .then(function(r){return r.json()})
    .then(function(d){data=d})
    .catch(function(){});
  var timer;
  input.addEventListener('input',function(){
    clearTimeout(timer);
    timer=setTimeout(function(){doSearch()},200);
  });
  function doSearch(){
    var q=input.value.trim().toLowerCase();
    if(q.length<2){results.innerHTML='';return;}
    var hits=data.filter(function(o){
      return(o.st||'').toLowerCase().indexOf(q)>=0;
    }).slice(0,30);
    if(!hits.length){results.innerHTML='<p style="color:#999">該当する事業所が見つかりません</p>';return;}
    var html=hits.map(function(o){
      return '<div class="card" style="margin-bottom:8px"><h3><a href="/office/'+o.slug+'.html">'+esc(o.n)+'</a></h3>'
        +'<div class="meta"><span>'+esc(o.a)+'</span>'
        +(o.tel?'<span>TEL: '+esc(o.tel)+'</span>':'')
        +'</div></div>';
    }).join('');
    results.innerHTML=html;
  }
  function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
})();
"""

# =============================================================
# HTML生成ヘルパー
# =============================================================

def make_head(title, desc, canonical, extra_head=''):
    """<head> タグを生成。訪問診療ナビと同一パターン"""
    ga_tag = ''
    if GA4_ID:
        ga_tag = f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{GA4_ID}');</script>'''
    return f"""<!DOCTYPE html>
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
  {ga_tag}
{extra_head}
</head>
"""


def make_header():
    return f"""<header>
  <div class="header-inner">
    <div>
      <a href="/" class="site-title">{h(SITE_NAME)}</a>
      <div class="site-subtitle">全国の{ENTITY_TYPE}を検索</div>
    </div>
    <nav>
      <a href="/about.html">運営者情報</a>
    </nav>
  </div>
</header>
"""


def make_breadcrumb(items):
    """パンくず生成。items = [(label, url), ...]  最後の要素はリンクなし"""
    parts = []
    for i, (label, url) in enumerate(items):
        if i == len(items) - 1:
            parts.append(f'<span>{h(label)}</span>')
        else:
            parts.append(f'<a href="{h(url)}">{h(label)}</a>')
    # JSON-LD BreadcrumbList
    ld_items = []
    for i, (label, url) in enumerate(items):
        full_url = url if url.startswith('http') else f'{SITE_URL}{url}'
        ld_items.append(f'{{"@type":"ListItem","position":{i+1},"name":"{h(label)}","item":"{h(full_url)}"}}')
    json_ld = f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{",".join(ld_items)}]}}</script>'
    return f'<nav class="breadcrumb">{" &gt; ".join(parts)}</nav>\n{json_ld}'


def make_footer(pref_data):
    """フッター。全47都道府県リンク付き"""
    pref_links = []
    for region_name, codes in REGIONS:
        links = []
        for code in codes:
            slug = PREF_SLUG.get(code, code)
            name = pref_data.get(code, {}).get('name', PREF_CODE_TO_NAME.get(code, ''))
            cnt = pref_data.get(code, {}).get('count', 0)
            links.append(f'<a href="/pref/{slug}.html">{h(name)}({cnt})</a>')
        pref_links.append(f'<div style="margin-bottom:8px"><strong>{h(region_name)}</strong><div class="footer-pref-grid">{"".join(links)}</div></div>')

    return f"""<footer>
  <div class="footer-inner">
    <p><strong>{h(SITE_NAME)}</strong> — 全国の{ENTITY_TYPE}を都道府県・市区町村から検索できるポータルサイト</p>
    <div style="margin-top:16px">{''.join(pref_links)}</div>
    <p style="font-size:0.75em;color:#aaa;margin-top:8px">データ出典: {h(ATTRIBUTION)}</p>
    <div class="footer-bottom">&copy; 2025 {h(SITE_NAME)} ({h(OPERATOR_NAME)})</div>
  </div>
</footer>
</body></html>
"""


# =============================================================
# ページ生成関数
# =============================================================

def build_index(offices_by_pref, pref_data, total_count):
    """トップページ"""
    title = f'{SITE_NAME}｜全国{total_count:,}件の{ENTITY_TYPE}を検索'
    desc = f'全国{total_count:,}件の{ENTITY_TYPE}を都道府県・市区町村から検索できます。住所・電話番号・営業日を掲載。'
    canonical = f'{SITE_URL}/'

    # 地域ブロック別リンク
    region_html = ''
    for region_name, codes in REGIONS:
        links = []
        for code in codes:
            slug = PREF_SLUG.get(code, code)
            name = pref_data.get(code, {}).get('name', PREF_CODE_TO_NAME.get(code, ''))
            cnt = pref_data.get(code, {}).get('count', 0)
            links.append(f'<a href="/pref/{slug}.html" class="pref-link">{h(name)} ({cnt})</a>')
        region_html += f'<div class="region-section"><h3>{h(region_name)}</h3><div class="pref-grid">{"".join(links)}</div></div>\n'

    body = f"""<body>
{make_header()}
<div class="container">
  <h1>{h(SITE_NAME)}</h1>
  <p style="margin:12px 0;font-size:1.05em">全国<strong>{total_count:,}件</strong>の{ENTITY_TYPE}を都道府県・市区町村から検索できます。</p>
  <p style="margin-bottom:20px;color:#666">ケアマネジャー（介護支援専門員）の所属する事業所を探せるポータルサイトです。住所・電話番号・営業日・法人名を掲載しています。</p>

  <div class="stats-bar">
    <div class="stat-box"><div class="num">{total_count:,}</div><div class="label">掲載{ENTITY_NAME}数</div></div>
    <div class="stat-box"><div class="num">47</div><div class="label">都道府県</div></div>
  </div>

  <h2 style="margin-top:32px;font-size:1.2em">都道府県から探す</h2>
  {region_html}
</div>
{make_footer(pref_data)}"""

    return make_head(title, desc, canonical) + body


def build_pref_page(pref_code, pref_name, offices, cities_data, pref_data):
    """都道府県ページ"""
    slug = PREF_SLUG.get(pref_code, pref_code)
    n = len(offices)
    title = f'{pref_name}の{ENTITY_TYPE}一覧（{n}件）【2025年】| {SITE_NAME}'
    desc = f'{pref_name}の{ENTITY_TYPE}を{n}件掲載。市区町村別に検索できます。住所・電話番号・営業日を一覧で確認。'
    canonical = f'{SITE_URL}/pref/{slug}.html'

    bc = make_breadcrumb([('トップ', '/'), (pref_name, '')])

    # 市区町村リスト（件数降順）
    city_items = sorted(cities_data.items(), key=lambda x: -len(x[1]))
    city_html = '<div class="city-grid">'
    for cname, coffices in city_items:
        cslug = city_slug(cname)
        city_html += f'<a href="/pref/{slug}/{cslug}.html" class="city-link">{h(cname)} ({len(coffices)})</a>'
    city_html += '</div>'

    # 事業所一覧カード
    cards = ''
    sorted_offices = sorted(offices, key=lambda o: (o.get('city', ''), o.get('name', '')))
    for o in sorted_offices:
        oslug = office_slug(o['office_id'])
        cards += f'''<div class="card">
  <h3><a href="/office/{oslug}.html">{h(o.get("name"))}</a></h3>
  <div class="meta">
    <span>{h(o.get("address"))}</span><br>
    {f'<span>TEL: {h(o.get("tel"))}</span>' if o.get("tel") else ''}
    {f'<span>{h(o.get("corporation_name"))}</span>' if o.get("corporation_name") else ''}
  </div>
</div>
'''

    body = f"""<body data-pref-code="{pref_code}">
{make_header()}
{bc}
<div class="container">
  <h1>{h(pref_name)}の{ENTITY_TYPE}一覧</h1>
  <p style="margin:8px 0;color:#666">{h(pref_name)}には<strong>{n}件</strong>の{ENTITY_TYPE}があります。</p>

  <div class="search-box">
    <input type="text" id="search-input" placeholder="{h(pref_name)}の{ENTITY_NAME}を検索（名称・住所・法人名）">
    <div id="search-results"></div>
  </div>

  <h2 style="margin-top:24px;font-size:1.1em">市区町村から探す</h2>
  {city_html}

  <h2 style="margin-top:24px;font-size:1.1em">{h(pref_name)}の{ENTITY_NAME}一覧（{n}件）</h2>
  <div class="card-grid">
    {cards}
  </div>
</div>
{make_footer(pref_data)}"""

    extra = '<script src="/static/search.js" defer></script>'
    return make_head(title, desc, canonical, extra) + body


def build_city_page(pref_code, pref_name, city_name_val, offices, pref_data):
    """市区町村ページ"""
    pslug = PREF_SLUG.get(pref_code, pref_code)
    cslug = city_slug(city_name_val)
    n = len(offices)
    title = f'{city_name_val}（{pref_name}）の{ENTITY_TYPE}一覧（{n}件） | {SITE_NAME}'
    desc = f'{pref_name}{city_name_val}の{ENTITY_TYPE}を{n}件掲載。住所・電話番号・営業日を一覧で確認できます。'
    canonical = f'{SITE_URL}/pref/{pslug}/{cslug}.html'

    bc = make_breadcrumb([
        ('トップ', '/'),
        (pref_name, f'/pref/{pslug}.html'),
        (city_name_val, ''),
    ])

    cards = ''
    sorted_offices = sorted(offices, key=lambda o: o.get('name', ''))
    for o in sorted_offices:
        oslug = office_slug(o['office_id'])
        bdays = o.get('business_days_text', '')
        cards += f'''<div class="card">
  <h3><a href="/office/{oslug}.html">{h(o.get("name"))}</a></h3>
  <div class="meta">
    <span>{h(o.get("address"))}</span><br>
    {f'<span>TEL: {h(o.get("tel"))}</span>' if o.get("tel") else ''}
    {f'<span>営業: {h(bdays)}</span>' if bdays else ''}
    {f'<span>{h(o.get("corporation_name"))}</span>' if o.get("corporation_name") else ''}
  </div>
</div>
'''

    body = f"""<body>
{make_header()}
{bc}
<div class="container">
  <h1>{h(city_name_val)}（{h(pref_name)}）の{ENTITY_TYPE}</h1>
  <p style="margin:8px 0;color:#666">{h(city_name_val)}には<strong>{n}件</strong>の{ENTITY_TYPE}があります。</p>

  <div class="card-grid">
    {cards}
  </div>

  <p style="margin-top:24px"><a href="/pref/{pslug}.html">&larr; {h(pref_name)}の{ENTITY_NAME}一覧に戻る</a></p>
</div>
{make_footer(pref_data)}"""

    return make_head(title, desc, canonical) + body


def build_office_page(o, pref_name, pref_data):
    """事業所詳細ページ"""
    oslug = office_slug(o['office_id'])
    pref_code = o.get('pref_code', '')
    pslug = PREF_SLUG.get(pref_code, pref_code)
    city_name_val = o.get('city', '')
    cslug = city_slug(city_name_val)

    name = o.get('name', '')
    title = f'{name} | {city_name_val}（{pref_name}）の{ENTITY_TYPE} | {SITE_NAME}'
    desc = f'{name}（{pref_name}{city_name_val}）の情報。住所・電話番号・営業日・法人情報を掲載。'
    canonical = f'{SITE_URL}/office/{oslug}.html'

    bc = make_breadcrumb([
        ('トップ', '/'),
        (pref_name, f'/pref/{pslug}.html'),
        (city_name_val, f'/pref/{pslug}/{cslug}.html'),
        (name, ''),
    ])

    # 情報テーブル
    rows = []
    def add_row(label, val):
        if val:
            rows.append(f'<tr><th>{h(label)}</th><td>{val}</td></tr>')

    add_row('事業所名', h(name))
    if o.get('name_kana'):
        add_row('フリガナ', h(o['name_kana']))
    add_row('住所', h(o.get('address', '')))
    if o.get('address_building'):
        add_row('建物名等', h(o['address_building']))
    if o.get('tel'):
        add_row('電話番号', f'<a href="tel:{h(o["tel"])}">{h(o["tel"])}</a>')
    if o.get('fax'):
        add_row('FAX', h(o['fax']))
    if o.get('business_days_text'):
        bdays = h(o['business_days_text'])
        if o.get('business_days_note'):
            bdays += f' <span style="color:#888">({h(o["business_days_note"])})</span>'
        add_row('営業日', bdays)
    if o.get('capacity'):
        add_row('定員', f'{o["capacity"]}名')
    if o.get('corporation_name'):
        add_row('法人名', h(o['corporation_name']))
    if o.get('office_code'):
        add_row('事業所番号', h(o['office_code']))
    if o.get('website_url'):
        url = o['website_url']
        add_row('公式サイト', f'<a href="{h(url)}" target="_blank" rel="noopener">{h(url)}</a>')

    table_html = f'<table class="info-table">{"".join(rows)}</table>'

    # 地図（OpenStreetMap embed — 無料）
    lat = o.get('latitude')
    lng = o.get('longitude')
    map_html = ''
    if lat and lng:
        map_html = f'''<div class="map-container">
  <iframe width="100%" height="300" frameborder="0" style="border:0"
    src="https://www.openstreetmap.org/export/embed.html?bbox={lng-0.005},{lat-0.003},{lng+0.005},{lat+0.003}&layer=mapnik&marker={lat},{lng}"
    loading="lazy" title="地図"></iframe>
  <p style="font-size:0.8em;color:#888;margin-top:4px">
    <a href="https://www.google.com/maps?q={lat},{lng}" target="_blank" rel="noopener">Google Mapsで見る</a>
  </p>
</div>'''

    # JSON-LD (LocalBusiness)
    json_ld_data = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": name,
        "address": {
            "@type": "PostalAddress",
            "addressRegion": pref_name,
            "addressLocality": city_name_val,
            "streetAddress": o.get('address', ''),
            "addressCountry": "JP",
        },
    }
    if o.get('tel'):
        json_ld_data["telephone"] = o['tel']
    if lat and lng:
        json_ld_data["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}
    if o.get('website_url'):
        json_ld_data["url"] = o['website_url']

    json_ld_tag = f'<script type="application/ld+json">{json.dumps(json_ld_data, ensure_ascii=False)}</script>'

    body = f"""<body>
{make_header()}
{bc}
<div class="container">
  <div class="detail-header">
    <h1>{h(name)}</h1>
    {f'<div class="kana">{h(o.get("name_kana"))}</div>' if o.get("name_kana") else ''}
  </div>

  {table_html}
  {map_html}

  <div style="margin-top:24px;display:flex;gap:12px;flex-wrap:wrap">
    <a href="/pref/{pslug}/{cslug}.html">&larr; {h(city_name_val)}の{ENTITY_NAME}一覧</a>
    <a href="/pref/{pslug}.html">&larr; {h(pref_name)}の{ENTITY_NAME}一覧</a>
  </div>
</div>
{make_footer(pref_data)}"""

    return make_head(title, desc, canonical, json_ld_tag) + body


def build_about_page(pref_data, total_count):
    """運営者情報ページ"""
    title = f'運営者情報 | {SITE_NAME}'
    desc = f'{SITE_NAME}の運営者情報。'
    canonical = f'{SITE_URL}/about.html'
    bc = make_breadcrumb([('トップ', '/'), ('運営者情報', '')])

    body = f"""<body>
{make_header()}
{bc}
<div class="container">
  <h1>運営者情報</h1>
  <table class="info-table">
    <tr><th>サイト名</th><td>{h(SITE_NAME)}</td></tr>
    <tr><th>運営者</th><td>{h(OPERATOR_NAME)}</td></tr>
    <tr><th>掲載件数</th><td>{total_count:,}件</td></tr>
    <tr><th>データ出典</th><td>{h(ATTRIBUTION)}</td></tr>
    <tr><th>ライセンス</th><td>CC BY 4.0（出典明記で商用利用可）</td></tr>
  </table>
  <p style="margin-top:16px"><a href="/">&larr; トップに戻る</a></p>
</div>
{make_footer(pref_data)}"""
    return make_head(title, desc, canonical) + body


# =============================================================
# JSON生成
# =============================================================

def generate_search_json(offices_by_pref, search_dir):
    """都道府県別検索JSON"""
    search_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for pref_code, offices in sorted(offices_by_pref.items()):
        entries = []
        for o in offices:
            # 検索用テキスト: 名称+カナ+住所+法人名+電話を結合
            search_text = ' '.join(filter(None, [
                o.get('name', ''),
                o.get('name_kana', ''),
                o.get('city', ''),
                o.get('address', ''),
                o.get('corporation_name', ''),
                o.get('tel', ''),
            ]))
            entries.append({
                'slug': office_slug(o['office_id']),
                'n': o.get('name', ''),
                'nk': o.get('name_kana', ''),
                'c': o.get('city', ''),
                'cc': o.get('city_code', ''),
                'a': o.get('address', ''),
                'tel': o.get('tel', ''),
                'cn': o.get('corporation_name', ''),
                'url': o.get('website_url', ''),
                'lat': o.get('latitude'),
                'lng': o.get('longitude'),
                'st': search_text,
            })
        path = search_dir / f'{pref_code}.json'
        path.write_text(
            json.dumps(entries, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8')
        total += len(entries)
    return total


def generate_geo_json(offices, path):
    """地図用軽量JSON"""
    geo = []
    for o in offices:
        lat = o.get('latitude')
        lng = o.get('longitude')
        if lat and lng:
            geo.append({
                'id': office_slug(o['office_id']),
                'n': o.get('name', ''),
                'pc': o.get('pref_code', ''),
                'cc': o.get('city_code', ''),
                'c': o.get('city', ''),
                'a': o.get('address', ''),
                'lt': round(lat, 5),
                'lg': round(lng, 5),
            })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(geo, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8')
    return len(geo)


def generate_stats_json(offices_by_pref, pref_data, total, path):
    """統計JSON"""
    stats = {
        'total': total,
        'prefectures': len(offices_by_pref),
        'by_prefecture': {code: {'name': pref_data[code]['name'], 'count': pref_data[code]['count']}
                          for code in sorted(pref_data.keys())},
        'generated_at': date.today().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')


def generate_sitemap(offices, offices_by_pref, city_urls, dist_dir):
    """sitemap.xml"""
    today = date.today().isoformat()
    urls = []
    urls.append((f'{SITE_URL}/', '1.0', 'weekly'))
    for code in sorted(offices_by_pref.keys()):
        slug = PREF_SLUG.get(code, code)
        urls.append((f'{SITE_URL}/pref/{slug}.html', '0.8', 'weekly'))
    for cu in city_urls:
        urls.append((cu, '0.7', 'weekly'))
    for o in offices:
        oslug = office_slug(o['office_id'])
        urls.append((f'{SITE_URL}/office/{oslug}.html', '0.5', 'monthly'))
    urls.append((f'{SITE_URL}/about.html', '0.3', 'yearly'))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, pri, freq in urls:
        lines.append(f'  <url><loc>{h(url)}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')
    lines.append('</urlset>')

    (dist_dir / 'sitemap.xml').write_text('\n'.join(lines), encoding='utf-8')
    return len(urls)


def generate_robots(dist_dir):
    """robots.txt"""
    txt = f"""User-agent: *
Disallow: /data/
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: Google-Extended
Disallow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    (dist_dir / 'robots.txt').write_text(txt, encoding='utf-8')


# =============================================================
# メインビルド
# =============================================================

def build_site():
    print(f'=== {SITE_NAME} サイト生成 ===')

    # データ読み込み
    if not DATA_FILE.exists():
        print(f'ERROR: {DATA_FILE} が見つかりません。先に scripts/normalize.py を実行してください。')
        sys.exit(1)

    with open(DATA_FILE, encoding='utf-8') as f:
        offices = json.load(f)
    total = len(offices)
    print(f'データ読込: {total:,}件')

    # is_active=false を除外
    offices = [o for o in offices if o.get('is_active', True)]
    print(f'有効事業所: {len(offices):,}件')

    # 都道府県別グルーピング
    offices_by_pref = defaultdict(list)
    for o in offices:
        code = o.get('pref_code', '')
        if code:
            offices_by_pref[code].append(o)

    pref_data = {}
    for code, olist in offices_by_pref.items():
        pref_data[code] = {
            'name': PREF_CODE_TO_NAME.get(code, olist[0].get('prefecture', '')),
            'count': len(olist),
        }

    print(f'都道府県数: {len(offices_by_pref)}')

    # 出力ディレクトリ作成
    for d in [DIST_DIR, DIST_DIR / 'pref', DIST_DIR / 'office', DIST_DIR / 'static', DIST_DIR / 'data']:
        d.mkdir(parents=True, exist_ok=True)

    # CSS/JS
    (DIST_DIR / 'static' / 'style.css').write_text(COMMON_CSS, encoding='utf-8')
    (DIST_DIR / 'static' / 'search.js').write_text(SEARCH_JS, encoding='utf-8')
    print('CSS/JS 生成完了')

    # トップページ
    idx = build_index(offices_by_pref, pref_data, len(offices))
    (DIST_DIR / 'index.html').write_text(idx, encoding='utf-8')
    print('index.html 生成完了')

    # 都道府県ページ + 市区町村ページ
    city_page_count = 0
    city_url_list = []
    for code, pref_offices in offices_by_pref.items():
        slug = PREF_SLUG.get(code, code)
        pref_name = pref_data[code]['name']

        # 市区町村別グルーピング
        cities = defaultdict(list)
        for o in pref_offices:
            c = o.get('city', 'その他') or 'その他'
            cities[c].append(o)

        # 都道府県ページ
        html = build_pref_page(code, pref_name, pref_offices, cities, pref_data)
        (DIST_DIR / 'pref' / f'{slug}.html').write_text(html, encoding='utf-8')

        # 市区町村ページ
        pref_city_dir = DIST_DIR / 'pref' / slug
        pref_city_dir.mkdir(parents=True, exist_ok=True)
        for cname, coffices in cities.items():
            cslug = city_slug(cname)
            html = build_city_page(code, pref_name, cname, coffices, pref_data)
            (pref_city_dir / f'{cslug}.html').write_text(html, encoding='utf-8')
            city_page_count += 1
            if len(coffices) >= 2:
                city_url_list.append(f'{SITE_URL}/pref/{slug}/{quote(cslug, safe="")}.html')

    print(f'都道府県ページ {len(offices_by_pref)}枚 + 市区町村ページ {city_page_count}枚 生成完了')

    # 事業所詳細ページ
    for o in offices:
        oslug = office_slug(o['office_id'])
        pref_code = o.get('pref_code', '')
        pref_name = pref_data.get(pref_code, {}).get('name', '')
        html = build_office_page(o, pref_name, pref_data)
        (DIST_DIR / 'office' / f'{oslug}.html').write_text(html, encoding='utf-8')
    print(f'詳細ページ {len(offices):,}枚 生成完了')

    # 運営者情報ページ
    about = build_about_page(pref_data, len(offices))
    (DIST_DIR / 'about.html').write_text(about, encoding='utf-8')
    print('about.html 生成完了')

    # 検索JSON
    search_dir = DIST_DIR / 'data' / 'search'
    search_count = generate_search_json(offices_by_pref, search_dir)
    print(f'検索JSON {search_count:,}件 → {len(offices_by_pref)}都道府県に分割')

    # 地図用JSON
    geo_count = generate_geo_json(offices, DIST_DIR / 'data' / 'offices_geo.json')
    print(f'地図用JSON {geo_count:,}件')

    # 統計JSON
    generate_stats_json(offices_by_pref, pref_data, len(offices), DIST_DIR / 'data' / 'stats.json')
    print('stats.json 生成完了')

    # sitemap.xml
    sitemap_count = generate_sitemap(offices, offices_by_pref, city_url_list, DIST_DIR)
    print(f'sitemap.xml {sitemap_count:,} URL')

    # robots.txt
    generate_robots(DIST_DIR)
    print('robots.txt 生成完了')

    # CNAME / .nojekyll (GitHub Pages用)
    (DIST_DIR / '.nojekyll').write_text('', encoding='utf-8')
    cname = CFG.get('cname_domain', '')
    if cname:
        (DIST_DIR / 'CNAME').write_text(cname + '\n', encoding='utf-8')
        print(f'CNAME 生成完了: {cname}')

    # 404ページ
    page_404 = make_head(f'ページが見つかりません | {SITE_NAME}',
                         f'指定されたページは存在しません。',
                         f'{SITE_URL}/404.html')
    page_404 += f"""<body>
{make_header()}
<div class="container" style="text-align:center;padding:60px 20px">
  <h1 style="font-size:2em;color:#999">404</h1>
  <p style="margin:16px 0">お探しのページが見つかりませんでした。</p>
  <a href="/">トップページへ</a>
</div>
{make_footer(pref_data)}"""
    (DIST_DIR / '404.html').write_text(page_404, encoding='utf-8')
    print('404.html 生成完了')

    # === 品質チェック ===
    print(f'\n{"=" * 60}')
    print(f'  ビルド完了 品質チェック')
    print(f'{"=" * 60}')
    pref_pages = len(list((DIST_DIR / 'pref').glob('*.html')))
    office_pages = len(list((DIST_DIR / 'office').glob('*.html')))
    search_files = len(list(search_dir.glob('*.json')))
    print(f'  総事業所数: {len(offices):,}')
    print(f'  都道府県ページ: {pref_pages}')
    print(f'  市区町村ページ: {city_page_count}')
    print(f'  詳細ページ: {office_pages:,}')
    print(f'  検索JSON: {search_files}ファイル ({search_count:,}件)')
    print(f'  地図JSON: {geo_count:,}件')
    print(f'  sitemap URL: {sitemap_count:,}')

    ok = True
    if pref_pages != 47:
        print(f'  [WARN] 都道府県ページが47ではない: {pref_pages}')
        ok = False
    if office_pages != len(offices):
        print(f'  [WARN] 詳細ページ数不一致: {office_pages} vs {len(offices)}')
        ok = False
    if search_files != 47:
        print(f'  [WARN] 検索JSONが47ではない: {search_files}')
        ok = False

    if ok:
        print(f'  [OK] 全チェック通過')
    print(f'{"=" * 60}')

    # プレビューサーバー
    if '--preview' in sys.argv:
        import http.server
        import functools
        os.chdir(str(DIST_DIR))
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST_DIR))
        server = http.server.HTTPServer(('localhost', 8000), handler)
        print(f'\nプレビュー: http://localhost:8000/')
        server.serve_forever()


if __name__ == '__main__':
    build_site()
