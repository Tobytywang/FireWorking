(function(){
  var host=document.getElementById('stats');
  var cards=[].slice.call(host.querySelectorAll('.stat'));
  [].slice.call(host.querySelectorAll('.cluster')).forEach(function(g){
    var n=g.querySelector('.cluster-h').textContent.trim();
    [].slice.call(g.querySelectorAll('.stat')).forEach(function(c){ c.dataset.g=n; });
  });
  var grid=document.createElement('div'); grid.className='cluster-grid';
  grid.style.cssText='display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px';
  host.innerHTML='';
  cards.forEach(function(c){ grid.appendChild(c); });
  host.appendChild(grid);
})();
