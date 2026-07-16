/* 多標籤快選：預設 + 用過的工項，可點選、可自訂 */
function TagPick(mountId, presets, selectedCSV){
  const mount = document.getElementById(mountId);
  const selected = new Set((selectedCSV||'').split(',').map(s=>s.trim()).filter(Boolean));
  let all = [...new Set([...selected, ...(presets||[])])];

  function render(){
    mount.innerHTML = '';
    all.forEach(t=>{
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = t;
      b.className = 'tp-chip' + (selected.has(t) ? ' on' : '');
      b.onclick = ()=>{ selected.has(t) ? selected.delete(t) : selected.add(t); render(); };
      mount.appendChild(b);
    });
    const add = document.createElement('button');
    add.type = 'button'; add.textContent = '＋自訂'; add.className = 'tp-add';
    add.onclick = ()=>{
      const v = prompt('新增工項標籤（可用逗號分隔多個）');
      if(v){ v.split(',').map(s=>s.trim()).filter(Boolean).forEach(x=>{
        selected.add(x); if(!all.includes(x)) all.push(x);
      }); render(); }
    };
    mount.appendChild(add);
  }
  render();
  return {
    value: ()=> [...selected].join(','),
    reset: (csv)=>{ selected.clear();
      (csv||'').split(',').map(s=>s.trim()).filter(Boolean).forEach(x=>{
        selected.add(x); if(!all.includes(x)) all.push(x); });
      render(); }
  };
}
window.TagPick = TagPick;
