async function refreshStudio(){
  const res = await fetch('/api/project');
  const data = await res.json();
  renderAssets(data.assets || []);
  renderReview(data.review || {});
}

function renderAssets(items){
  const root=document.querySelector('#assets');
  if(!root) return;
  root.innerHTML=items.map(x=>`
    <div class="asset">
      <b>${x.path}</b><br>
      SHA: ${(x.sha256||'').slice(0,12)}<br>
      ${x.size || 0} bytes
    </div>`).join('');
}

function renderReview(review){
  const root=document.querySelector('#review');
  if(!root) return;
  root.innerHTML=['script','storyboard','clip'].map(stage=>{
    const item=review[stage]||{status:'pending'};
    return `<div><b>${stage}</b>: ${item.status}
    <button onclick="approve('${stage}')">通过</button>
    <button onclick="reject('${stage}')">驳回</button></div>`;
  }).join('');
}

refreshStudio();
setInterval(refreshStudio,3000);
