// The public website submits to the real tenant-scoped support API.
const form=document.getElementById('websiteComplaint');
const dialog=document.getElementById('websiteComplaintDialog');
const error=document.getElementById('websiteComplaintError');
const topics={wifi:'Wi-Fi support request',maintenance:'Repairs and maintenance',cleaning:'Cleaning concern',access:'Room or building access',utilities:'Water or utilities enquiry',billing:'Billing or other enquiry'};
let busy=false,attempt=null,returnFocus=null;

function openComplaint(link){
    returnFocus=link;form.reset();error.textContent='';attempt=null;
    const topic=new URL(link.href,location.href).searchParams.get('topic');
    form.elements.title.value=Object.hasOwn(topics,topic)?topics[topic]:'';
    dialog.showModal();form.elements.access_key.focus();
}
for(const link of document.querySelectorAll('a[href$="#report"]')){
    link.addEventListener('click',event=>{event.preventDefault();openComplaint(link);});
}
document.getElementById('closeWebsiteComplaint').onclick=()=>{if(!busy)dialog.close();};
dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
dialog.addEventListener('close',()=>{form.reset();error.textContent='';attempt=null;returnFocus?.focus();});
form.onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    // Read values before disabling controls: disabled fields are omitted by FormData.
    const values=Object.fromEntries(new FormData(form));
    const key=values.access_key.trim();
    const payload={title:values.title,description:values.description};
    const signature=JSON.stringify([key,payload]);
    if(!attempt||attempt.signature!==signature)attempt={signature,id:crypto.randomUUID()};
    const locked=[...dialog.querySelectorAll('button,input,textarea')].filter(el=>!el.disabled);
    locked.forEach(el=>el.disabled=true);busy=true;error.textContent='';
    const button=document.getElementById('sendWebsiteComplaint');button.textContent='Sending…';
    let receipt=null;
    try{
        const response=await fetch('/api/website/complaints',{method:'POST',credentials:'omit',headers:{
            'Authorization':'Bearer '+key,'Content-Type':'application/json','Idempotency-Key':attempt.id},body:JSON.stringify(payload)});
        const result=await response.json();
        if(!response.ok)throw Error(result.error||'The complaint could not be accepted. Check your details.');
        if(typeof result.id!=='string'||!/^BL-[A-F0-9]{10}$/.test(result.id))throw Error('No valid case reference was confirmed. Check My requests before starting a new complaint.');
        receipt=result;
    }catch(problem){
        error.textContent=problem instanceof TypeError?'Could not confirm submission. Your details are kept; retrying uses the same request reference.':problem.message;
    }finally{
        locked.forEach(el=>el.disabled=false);busy=false;button.textContent='Submit complaint';
    }
    if(receipt){
        document.getElementById('websiteCaseRef').textContent=receipt.id;
        document.getElementById('websiteTrackCase').href='/portal?case='+encodeURIComponent(receipt.id)+'#conversations';
        document.getElementById('websiteStaffCase').href='/?case='+encodeURIComponent(receipt.id);
        returnFocus=null;dialog.close();
        const card=document.getElementById('websiteReceipt');card.hidden=false;
        card.scrollIntoView({block:'start'});document.getElementById('websiteReceiptTitle').focus({preventScroll:true});
    }
};
