async function approve(stage){
  await fetch('/api/review', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({stage,status:'approved'})
  });
  refreshStudio();
}

async function reject(stage){
  await fetch('/api/review', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({stage,status:'rejected'})
  });
  refreshStudio();
}
