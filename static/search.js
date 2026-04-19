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
      var cat=o.cat||'caremanager';
      return '<div class="card" style="margin-bottom:8px"><h3><a href="/'+cat+'/'+o.slug+'.html">'+esc(o.n)+'</a></h3>'
        +'<div class="meta"><span>'+esc(o.a)+'</span>'
        +(o.tel?'<span>TEL: '+esc(o.tel)+'</span>':'')
        +'</div></div>';
    }).join('');
    results.innerHTML=html;
  }
  function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
})();
