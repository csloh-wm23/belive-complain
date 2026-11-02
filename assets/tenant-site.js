fetch('/api/demo').then(r=>r.json()).then(d=>{document.querySelectorAll('[data-demo-link]').forEach(a=>a.hidden=!d.available);}).catch(()=>{});
