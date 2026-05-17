(function(){
  'use strict';
  var checkboxes=document.querySelectorAll('[data-filter]');
  if(!checkboxes.length)return;
  var countEl=document.getElementById('filter-count');

  function applyFilters(){
    var active=[];
    checkboxes.forEach(function(cb){if(cb.checked)active.push(cb.dataset.filter);});
    var cards=document.querySelectorAll('.caremanager-card');
    var shown=0;
    cards.forEach(function(card){
      var hide=false;
      if(active.length){
        active.forEach(function(f){
          var val=card.dataset[toCamel(f)];
          // trueのカードのみ表示、null(未取得)はfilter対象外
          if(val!=='true')hide=true;
        });
      }
      if(hide){card.classList.add('care-card-hidden');}
      else{card.classList.remove('care-card-hidden');shown++;}
    });
    if(countEl){
      if(active.length){
        countEl.textContent=shown+'件を表示中';
        countEl.style.display='block';
      }else{
        countEl.style.display='none';
      }
    }
  }

  function toCamel(s){
    // terminal_care_addon → terminalCareAddon (for dataset access)
    return s.replace(/_([a-z])/g,function(_,c){return c.toUpperCase();});
  }

  checkboxes.forEach(function(cb){cb.addEventListener('change',applyFilters);});
})();
