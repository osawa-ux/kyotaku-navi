#!/usr/bin/env bash
# 公開後 spot check — care.zaitaku-navi.com
# 使い方: bash scripts/spot_check.sh [https|http]
#   デフォルトは https、HTTPS未発行時は `bash scripts/spot_check.sh http`

set -u
SCHEME="${1:-https}"
HOST="care.zaitaku-navi.com"
BASE="${SCHEME}://${HOST}"

pass=0
fail=0

check() {
  local name="$1" url="$2" expect="$3"
  local code
  code=$(curl -sI --max-time 15 -o /dev/null -w "%{http_code}" "$url")
  if [ "$code" = "$expect" ]; then
    echo "  [OK]   $name  ($code)  $url"
    pass=$((pass+1))
  else
    echo "  [FAIL] $name  expected $expect got $code  $url"
    fail=$((fail+1))
  fi
}

contains() {
  local name="$1" url="$2" needle="$3"
  local body
  body=$(curl -s --max-time 15 "$url")
  if echo "$body" | grep -q "$needle"; then
    echo "  [OK]   $name  contains: $needle"
    pass=$((pass+1))
  else
    echo "  [FAIL] $name  missing: $needle"
    fail=$((fail+1))
  fi
}

echo "=== HTTP status codes ==="
check "top"           "$BASE/"                                200
check "caremanager"   "$BASE/caremanager/"                    200
check "about"         "$BASE/about.html"                      200
check "pref/kanagawa" "$BASE/pref/kanagawa.html"              200
check "pref/tokyo"    "$BASE/pref/tokyo.html"                 200
check "pref/hokkaido" "$BASE/pref/hokkaido.html"              200
check "detail sample" "$BASE/caremanager/mhlw_kaigo_0110114501_430.html" 200
check "sitemap.xml"   "$BASE/sitemap.xml"                     200
check "robots.txt"    "$BASE/robots.txt"                      200
check "404 fallback"  "$BASE/no-such-page-xyz"                404

echo ""
echo "=== Content sanity ==="
contains "top title"        "$BASE/"                    "居宅介護支援ナビ"
contains "top canonical"    "$BASE/"                    'rel="canonical" href="https://care.zaitaku-navi.com/"'
contains "top og:url"       "$BASE/"                    'og:url" content="https://care.zaitaku-navi.com/"'
contains "sitemap urlset"   "$BASE/sitemap.xml"         "urlset"
contains "robots sitemap"   "$BASE/robots.txt"          "Sitemap: https://care.zaitaku-navi.com/sitemap.xml"
contains "detail JSON-LD"   "$BASE/caremanager/mhlw_kaigo_0110114501_430.html" '"@type": "LocalBusiness"'
contains "pref footer link" "$BASE/"                    '/pref/kanagawa.html'

echo ""
echo "=== Summary ==="
echo "  pass: $pass"
echo "  fail: $fail"
[ "$fail" -eq 0 ] && echo "  [ALL_GREEN]" && exit 0
echo "  [FAILED]"
exit 1
