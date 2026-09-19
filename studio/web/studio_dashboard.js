async function loadStudio(){
  const res=await fetch('/api/project');
  const data=await res.json();
  renderShots(data);
}

function renderShots(data){
  const root=document.querySelector('#shots');
  if(!root) return;
  root.innerHTML=(data.shots||[]).map(s=>`
    <section class="shot">
      <h3>${s.id||'shot'}</h3>
      <video controls src="${s.preview||''}"></video>
      <button onclick="approveShot('${s.id}')">通过视频</button>
    </section>`).join('');
}

async function approveShot(id){
 await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage:'clip',shot_id:id,action:'approve'})});
 loadStudio();
}

loadStudio();
setInterval(loadStudio,3000);
