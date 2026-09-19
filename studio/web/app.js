async function refreshStudio(){
  const res = await fetch('/api/project');
  const data = await res.json();
  renderAssets(data.assets);
  renderReview(data.review);
}

function renderAssets(items){
  const root=document.querySelector('#assets');
  if(!root) return;
  root.innerHTML=items.map(x=>`
    <div class="asset">
      <b>${x.path}</b><br>
      ${x.kind || ''} ${x.size || ''}
    </div>`).join('');
}

function renderReview(review){
  const root=document.querySelector('#review');
  if(!root) return;
  root.textContent=JSON.stringify(review,null,2);
}

refreshStudio();
setInterval(refreshStudio,3000);
