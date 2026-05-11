<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{{ PREF_NAME }}の{{ FILTER_LABEL }}に対応したケアマネ事業所（{{ OFFICE_COUNT }}件）| 居宅介護支援ナビ</title>
  <meta name="description" content="{{ PREF_NAME }}で{{ FILTER_LABEL }}に対応したケアマネジャー事業所を{{ OFFICE_COUNT }}件掲載。公表データに基づく代理指標で絞り込み。住所・電話番号・法人情報を掲載しています。">
  <link rel="canonical" href="{{ SITE_URL }}/feature/{{ PREF_SLUG }}-{{ FILTER_KEY }}.html">
  <link rel="stylesheet" href="/static/style.css">
  <!-- GA4 -->
  {{ GA4_TAG }}
</head>
<body>
  <!-- Header (shared component) -->
  {{ HEADER }}

  <!-- Breadcrumb -->
  <nav class="breadcrumb">
    <a href="/">トップ</a> &gt;
    <a href="/pref/{{ PREF_SLUG }}.html">{{ PREF_NAME }}</a> &gt;
    <span>{{ FILTER_LABEL }}対応</span>
  </nav>

  <div class="container">
    <h1>{{ PREF_NAME }}の{{ FILTER_LABEL }}に対応したケアマネ事業所</h1>

    <!-- 代理指標の説明（誤誘導防止のため必須）-->
    <div style="background:#fff3e0;border:1px solid #ffe0b2;border-radius:8px;padding:14px 16px;margin:16px 0;font-size:0.9em">
      <strong>このページについて</strong><br>
      掲載情報は<a href="https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html" target="_blank" rel="noopener">介護サービス情報公表システム（厚生労働省）</a>の公表データに基づく代理指標です。
      {{ FILTER_LABEL }}の算定実績は事業所の体制・経験の<strong>参考情報</strong>であり、医療依存度の確定的な判定や、特定の疾患・状態に対応できることを保証するものではありません。
      必ず直接事業所にご確認ください。
    </div>

    <!-- Stats -->
    <div class="stats-bar">
      <div class="stat-box">
        <div class="num">{{ OFFICE_COUNT }}</div>
        <div class="label">{{ FILTER_LABEL }}対応事業所</div>
      </div>
      <div class="stat-box">
        <div class="num">{{ PREF_NAME }}</div>
        <div class="label">対象エリア</div>
      </div>
    </div>

    <!-- 市区町村別リンク -->
    <h2 style="margin-top:24px;font-size:1.1em">市区町村から探す</h2>
    <div class="city-grid">
      {{ CITY_LINKS }}
    </div>

    <!-- 事業所一覧 -->
    <h2 style="margin-top:24px;font-size:1.1em">{{ PREF_NAME }}の{{ FILTER_LABEL }}対応ケアマネ事業所一覧（{{ OFFICE_COUNT }}件）</h2>
    <div class="card-grid">
      {{ OFFICE_CARDS }}
    </div>

    <!-- 関連リンク -->
    <div style="margin-top:32px;padding-top:16px;border-top:1px solid #e0e0e0">
      <h3 style="font-size:1em;margin-bottom:8px">他のフィルタで探す</h3>
      <ul style="list-style:none;display:flex;flex-wrap:wrap;gap:8px">
        {{ RELATED_FILTER_LINKS }}
      </ul>
    </div>

    <p style="margin-top:16px"><a href="/pref/{{ PREF_SLUG }}.html">&larr; {{ PREF_NAME }}の全ケアマネ事業所一覧</a></p>
  </div>

  {{ FOOTER }}
</body>
</html>
