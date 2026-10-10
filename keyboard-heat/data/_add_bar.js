(function(){
  var P=[62,9.3,58,72,45,38,45.2,66,52,88];
  [].slice.call(document.querySelectorAll('#stats .stat')).forEach(function(c,i){
    var b=document.createElement('div');
    b.setAttribute('data-inkbar','1');
    b.style.cssText='height:6px;border-radius:3px;background:#ece0d6;margin-top:9px;overflow:hidden';
    var f=document.createElement('i');
    f.style.cssText='display:block;height:100%;width:'+(P[i]||50)+'%;background:#e07a3f';
    b.appendChild(f); c.appendChild(b);
  });
})();
