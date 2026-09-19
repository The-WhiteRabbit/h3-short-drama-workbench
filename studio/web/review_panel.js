async function submitReview(stage, action, assetId=null){
  const payload = {
    stage,
    action,
    asset_id: assetId,
    timestamp: new Date().toISOString()
  };

  const res = await fetch('/api/review', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  });

  return await res.json();
}

function reviewButton(stage, action){
  return `<button onclick="submitReview('${stage}','${action}')">${action}</button>`;
}
