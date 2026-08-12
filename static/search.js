(function(){
  var input=document.getElementById('search-input');
  var results=document.getElementById('search-results');
  var data=[];
  var prefCode=document.body.dataset.prefCode||'';
  if(!prefCode||!input)return;
  var loadFailed=false;
  fetch('/care/data/search/'+prefCode+'.json')
    .then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})
    .then(function(d){data=d})
    // 握り潰すと読み込み失敗が「該当なし」に見える（2026-08-09 実測）
    .catch(function(){loadFailed=true;});
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
    if(loadFailed){results.innerHTML='<p style="color:#c62828">データの読み込みに失敗しました。ページを再読み込みしてください。</p>';return;}
    if(!hits.length){results.innerHTML='<p style="color:#999">該当する事業所が見つかりません</p>';return;}
    var html=hits.map(function(o){
      var cat=o.cat||'caremanager';
      // JS 生成リンクは edge の HTMLRewriter が届かないため base を焼き込む
      return '<div class="card" style="margin-bottom:8px"><h3><a href="/care/'+cat+'/'+o.slug+'.html">'+esc(o.n)+'</a></h3>'
        +'<div class="meta"><span>'+esc(o.a)+'</span>'
        +(o.tel?'<span>TEL: '+esc(o.tel)+'</span>':'')
        +'</div></div>';
    }).join('');
    results.innerHTML=html;
  }
  function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
})();
