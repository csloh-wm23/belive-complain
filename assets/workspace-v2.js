/* Reorganise the existing feature-complete UI into a simpler two-entry workspace.
   This runs before app.js so all existing IDs and event bindings stay intact. */
const nav=document.querySelector('.sidebar nav');
if(nav)nav.innerHTML=`
  <button data-view="overview" class="active">Command center</button>
  <button data-view="cases">Complaints <b id="navCount">0</b></button>
  <button data-view="memory">Self-learning</button>
  <details class="system-tools" open>
    <summary>System setup</summary>
    <div>
      <button data-view="settings">AI & knowledge</button>
      <button data-view="sources">Proactive sources</button>
      <button data-view="notifications">Messages</button>
      <button data-view="database">Data & backups</button>
      <button data-view="activity">Reports & activity</button>
    </div>
  </details>`;

const overview=document.querySelector('[data-page="overview"]');
if(overview)overview.innerHTML=`
  <section class="card command-hero">
    <span class="eyebrow">ONE SUPPORT SYSTEM · TWO WAYS TO ENTER</span>
    <h2>Find complaints early, or respond when tenants contact you.</h2>
    <p>Both sides enter one complaint queue. Hermes coordinates the work, staff step in only when safety, approval or physical action is required, and verified outcomes improve future handling.</p>
    <div class="entry-lanes">
      <article class="entry-lane proactive-lane">
        <span class="lane-number">SIDE A · PROACTIVE</span>
        <h3>We find the complaint</h3>
        <p>Monitor only approved public sources, detect likely complaints, remove duplicates and escalate critical issues quickly.</p>
        <div class="lane-status" id="proactiveSummary">Checking monitored sources…</div>
        <div class="lane-actions"><button class="primary" data-go="sources">Manage monitoring</button><button data-go="cases">View discovered cases</button></div>
      </article>
      <article class="entry-lane reactive-lane">
        <span class="lane-number">SIDE B · REACTIVE</span>
        <h3>The tenant comes to us</h3>
        <p>Receive private questions and complaints, answer safe routine enquiries and hand complex cases to staff with full context.</p>
        <div class="lane-status" id="reactiveSummary">Checking tenant requests…</div>
        <div class="lane-actions"><a href="/belive" target="_blank" rel="noopener">Open tenant website ↗</a><button class="primary" data-go="cases">Open complaint queue</button></div>
      </article>
    </div>
  </section>
  <section class="card agent-workflow">
    <div class="workflow-intro"><div><span class="eyebrow">FOUR LOGICAL HERMES ROLES</span><h2>One continuous complaint workflow</h2></div><p>The roles run only when needed. They share the same verified knowledge and case history; they do not represent four separate servers.</p></div>
    <div class="agent-grid">
      <div class="agent-card"><b>AGENT 01</b><strong>Complaint Manager</strong><span>Receives, classifies and prioritises every complaint.</span></div>
      <div class="agent-card"><b>AGENT 02</b><strong>External Monitoring</strong><span>Finds authorised public complaints and flags urgent risk.</span></div>
      <div class="agent-card"><b>AGENT 03</b><strong>Investigation & Resolution</strong><span>Uses approved knowledge to prepare safe assistance.</span></div>
      <div class="agent-card"><b>AGENT 04</b><strong>Follow-up & Escalation</strong><span>Tracks progress, waits for staff action and verifies outcomes.</span></div>
    </div>
    <div class="learning-loop"><span><b>Shared self-learning:</b> Closed case → verified outcome → reviewed lesson → reuse → measurable comparison</span><button data-go="memory">Open self-learning →</button></div>
  </section>
  <div class="metrics" id="metrics"></div>
  <div class="command-grid">
    <div>
      <section class="card"><div class="card-heading"><div><h2>Unified complaint queue</h2><p>Proactive and reactive complaints appear together.</p></div><button data-go="cases" class="text-button">View all →</button></div><div class="table-scroll"><table><thead><tr><th>Case</th><th>Urgency</th><th>Status</th><th>Owner</th><th>Next action / deadline</th></tr></thead><tbody id="recentCases"></tbody></table></div></section>
      <section class="card"><h2>Automatic support</h2><p id="routineSummary"></p><button class="text-button" data-admin data-go="settings">Manage AI knowledge & automation →</button></section>
    </div>
    <aside>
      <section class="card attention-card"><h2>Needs a person</h2><div id="attention"></div></section>
      <section class="card learning-pulse"><span class="eyebrow">SELF-LEARNING</span><strong id="learningCount">0</strong><h2>Reviewed lessons ready</h2><p id="learningSummary">Verified outcomes become reusable guidance only after review.</p><button class="text-button" data-go="memory">Review learning →</button></section>
    </aside>
  </div>`;

const memory=document.querySelector('[data-page="memory"]');
if(memory){
  memory.insertAdjacentHTML('afterbegin',`<section class="learning-hero"><span class="eyebrow">CONTROLLED SELF-LEARNING</span><h2>Learn from verified outcomes, not from every AI answer.</h2><p>Only a closed case with reviewed feedback can become a lesson. Rejected or reopened cases are revoked immediately, and property facts remain separate from writing-style memory.</p><div class="learning-steps"><div><b>01</b><strong>Close with evidence</strong><span>Staff verifies the real outcome.</span></div><div><b>02</b><strong>Review the lesson</strong><span>Approve or correct reusable wording.</span></div><div><b>03</b><strong>Test improvement</strong><span>Compare before and after outputs.</span></div><div><b>04</b><strong>Reuse or revoke</strong><span>Keep only measured, reviewed value.</span></div></div></section>`);
  const children=[...memory.children].filter(x=>!x.classList.contains('learning-hero'));
  const reviewed=children.at(-1);
  if(reviewed?.tagName==='DETAILS')reviewed.open=true;
  const lab=document.createElement('details');lab.className='learning-lab';lab.open=false;
  lab.innerHTML='<summary>Open the before/after learning lab</summary>';
  children.slice(0,-1).forEach(child=>lab.appendChild(child));
  memory.insertBefore(lab,reviewed);
}

const settings=document.querySelector('[data-page="settings"]');
if(settings){
  const groups=[
    {label:'AI & replies',intro:'Test the AI connection, manage automatic replies and edit approved knowledge.',ids:['checkAi','knowledgeForm']},
    {label:'Staff routing',intro:'Choose which team receives a complaint when it needs staff attention.',ids:['routingForm']},
    {label:'Properties & tenant access',intro:'Manage verified property and tenant records. Customers can submit and track complaints without a tenant account.',ids:['condoForm','tenantForm','recordForm','portalIssue','resources']},
    {label:'Staff accounts',intro:'Manage operator accounts and staff access.',ids:['usersList']},
    {label:'Demo',intro:'Set up a fictional account for testing.',ids:['prepareDemo']}
  ];
  const nav=document.createElement('nav');
  nav.className='setup-nav';
  nav.setAttribute('aria-label','System setup sections');
  settings.prepend(nav);
  const sections=groups.map(({label,intro,ids},index)=>{
    const panel=document.createElement('section');
    panel.className='setup-panel';
    panel.id='setup-section-'+index;
    panel.hidden=index!==0;
    const heading=document.createElement('h2');
    heading.textContent=label;
    const description=document.createElement('p');
    description.className='setup-description';
    description.textContent=intro;
    panel.append(heading,description);
    for(const id of ids){
      const card=document.getElementById(id)?.closest('.card');
      if(card)panel.append(card);
    }
    settings.append(panel);
    const button=document.createElement('button');
    button.type='button';
    button.textContent=label;
    button.setAttribute('aria-controls',panel.id);
    button.setAttribute('aria-pressed',String(index===0));
    button.addEventListener('click',()=>{
      sections.forEach(({panel,button},i)=>{
        panel.hidden=i!==index;
        button.setAttribute('aria-pressed',String(i===index));
      });
    });
    nav.append(button);
    return {panel,button};
  });
  const oldGrid=settings.querySelector(':scope > .settings-grid');
  if(oldGrid&&!oldGrid.children.length)oldGrid.remove();
  const accessCard=document.getElementById('portalIssue')?.closest('.card');
  const accessTitle=accessCard?.querySelector('h2');
  if(accessTitle)accessTitle.textContent='Verified tenant access';
  const accessNote=accessCard?.querySelector('p.muted');
  if(accessNote)accessNote.textContent='Issue a private access key only after verifying a tenant who needs their full complaint history.';
}

const sourceHeading=document.querySelector('[data-page="sources"] h2');
if(sourceHeading)sourceHeading.textContent='Proactive complaint discovery';
const sourceIntro=document.querySelector('[data-page="sources"] h2 + p');
if(sourceIntro)sourceIntro.textContent='Add an authorised source for each platform. Scans read up to 25 recent items per source while BeLive is running.';
const sourcesPage=document.querySelector('[data-page="sources"]');
if(sourcesPage){
  const monitor=document.createElement('section');
  monitor.className='card';
  monitor.innerHTML=`<h2>Automatic discovery</h2>
    <p id="scanSummary" role="status"></p>
    <form id="sourceScheduleForm" data-admin>
      <label>Check every (minutes)<input name="minutes" id="scanInterval" type="number" min="1" max="1440" required value="15"></label>
      <div class="case-actions"><button type="submit">Save interval</button>
      <button class="primary" id="scanAllSources" type="button">Scan all enabled sources now</button></div>
    </form>`;
  sourcesPage.prepend(monitor);
  const findings=document.createElement('section');
  findings.className='card';
  findings.innerHTML='<h2>Discovered complaints</h2><label>Platform<select id="discoveryPlatform"><option value="">All platforms</option><option value="GOOGLE">Google Reviews</option><option value="FACEBOOK">Facebook</option><option value="THREADS">Threads</option></select></label><div id="discoveryFindings"></div>';
  monitor.after(findings);
  const search=document.createElement('details');
  search.className='card';
  search.innerHTML=`<summary>Find or record a public complaint manually</summary>
    <form id="publicSearchForm">
      <label>Property, business or complaint keyword<input name="keyword" required maxlength="120" placeholder="e.g. Kuala Lumpur apartment maintenance"></label>
      <button type="submit">Show search links</button>
    </form>
    <div id="publicSearchLinks" class="case-actions" hidden></div>
    <p class="muted">Open a result and confirm it is public. Paste its link and a short summary to create a case for assessment.</p>
    <form id="publicComplaintForm">
      <label>Public review or post URL<input name="public_url" type="url" required maxlength="2000"></label>
      <label>Complaint title<input name="title" required minlength="4" maxlength="120"></label>
      <label>What was reported?<textarea name="description" required minlength="10" maxlength="6000"></textarea></label>
      <p class="form-error error" role="alert"></p>
      <button class="primary" type="submit">Save complaint and assess</button>
    </form>`;
  sourcesPage.append(search);
  document.getElementById('publicSearchForm').addEventListener('submit',event=>{
    event.preventDefault();
    const keyword=event.target.elements.keyword.value.trim();
    if(!keyword)return;
    const links=document.getElementById('publicSearchLinks');
    const targets=[
      ['Google Maps reviews','https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(keyword)],
      ['Facebook posts','https://www.facebook.com/search/posts/?q='+encodeURIComponent(keyword)],
      ['Threads posts','https://www.threads.com/search?q='+encodeURIComponent(keyword)]
    ];
    links.replaceChildren(...targets.map(([label,href])=>{
      const link=document.createElement('a');
      link.href=href;
      link.textContent=label;
      link.target='_blank';
      link.rel='noopener noreferrer';
      return link;
    }));
    links.hidden=false;
  });
}

const newCase=document.getElementById('newCase');
if(newCase)newCase.textContent='＋ Add complaint';
