fetch('/api/demo').then(r=>r.json()).then(d=>{document.querySelectorAll('[data-demo-link]').forEach(a=>a.hidden=!d.available);}).catch(()=>{});
fetch('/api/support-channel').then(r=>{if(!r.ok)throw Error('Channel unavailable');return r.json();}).then(channel=>{
  const note=document.getElementById('tenantReportStatus');if(!channel.available){if(note)note.textContent='WhatsApp support is being set up. You can still use the website complaint form.';return;}
  document.querySelectorAll('[data-whatsapp-report]').forEach(a=>{a.href=channel.chat_url;a.textContent='Customer Support · WhatsApp ↗';});
  document.querySelectorAll('.site-topic').forEach(a=>{const topic=a.querySelector('h3')?.textContent||'an issue';const url=new URL(channel.chat_url);url.searchParams.set('text',`Hi BeLive, I need help with ${topic}.`);a.href=url.href;});
  if(note)note.textContent=channel.automatic_replies_verified?'Continue your private conversation with Hermes in WhatsApp. You can send photos there.':'Open the company WhatsApp chat. Hermes automatic replies are still being connected.';
  const intro=document.querySelector('.site-lede');if(intro)intro.textContent='Ask questions, get information or request help in WhatsApp. Continue the conversation and share photos in the same chat.';
}).catch(()=>{const note=document.getElementById('tenantReportStatus');if(note)note.textContent='WhatsApp support is temporarily unavailable. You can use the website complaint form.';});
