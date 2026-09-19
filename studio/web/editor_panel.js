async function loadStudio(){
  const res = await fetch('/api/project');
  const data = await res.json();
  renderJobs(data.jobs || []);
  renderCandidates(data.candidates || []);
}

function renderJobs(items){
  const el=document.querySelector('#jobs');
  if(el) el.innerHTML=items.map(x=>`<div>${x.id || ''} ${x.status || ''}</div>`).join('');
}

function renderCandidates(items){
  const el=document.querySelector('#candidates');
  if(el) el.innerHTML=items.map(x=>`<div>${x.path || x.id || ''}</div>`).join('');
}

loadStudio();
setInterval(loadStudio,3000);
