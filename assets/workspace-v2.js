/* Reorganise the existing feature-complete UI into a simpler two-entry workspace.
   This runs before app.js so all existing IDs and event bindings stay intact. */
const nav=document.querySelector('.sidebar nav');
if(nav)nav.innerHTML=`
  <button data-view="overview" class="active">Command center</button>
  <button data-view="cases">Complaints <b id="navCount">0</b></button>
  <button data-view="sources">Public reviews</button>
  <button data-view="memory">Self-learning</button>
  <details class="system-tools">
    <summary>System setup</summary>
    <div>
      <button data-view="settings">AI & knowledge</button>
      <button data-view="notifications">Messages</button>
      <button data-view="database">Data & backups</button>
      <button data-view="activity">Reports & activity</button>
    </div>
  </details>`;

const overview=document.querySelector('[data-page="overview"]');
if(overview)overview.innerHTML=`
  <section class="card command-hero">
    <h2>Tenant support</h2>
    <div class="entry-lanes">
      <article class="entry-lane">
        <h3>Public reviews</h3>
        <p>Review reports collected from public sources and prepare replies for staff review.</p>
        <div class="lane-status" id="proactiveSummary"></div>
        <div class="lane-actions"><button class="primary" data-go="sources">Open public reviews</button></div>
      </article>
      <article class="entry-lane">
        <h3>Tenant complaints</h3>
        <p>Open the queue to review replies or take ownership of a case.</p>
        <div class="lane-status" id="reactiveSummary"></div>
        <div class="lane-actions"><button class="primary" data-go="cases">Open complaints</button></div>
      </article>
    </div>
  </section>
  <div class="metrics" id="metrics"></div>
  <div class="command-grid">
    <div>
      <section class="card"><div class="card-heading"><div><h2>Unified complaint queue</h2><p>Proactive and reactive complaints appear together.</p></div></div><div class="table-scroll"><table><thead><tr><th>Case</th><th>Urgency</th><th>Status</th><th>Owner</th><th>Next action / deadline</th></tr></thead><tbody id="recentCases"></tbody></table></div></section>
      <section class="card"><h2>Automatic support</h2><p id="routineSummary"></p></section>
    </div>
    <aside>
      <section class="card attention-card"><h2>Needs a person</h2><div id="attention"></div></section>
      <section class="card learning-pulse"><span class="eyebrow">SELF-LEARNING</span><strong id="learningCount">0</strong><h2>Reviewed lessons ready</h2><p id="learningSummary">Verified outcomes become reusable guidance only after review.</p></section>
    </aside>
  </div>`;

const memory=document.querySelector('[data-page="memory"]');
if(memory){
  memory.insertAdjacentHTML('afterbegin',`<section class="learning-hero"><span class="eyebrow">CONTROLLED SELF-LEARNING</span><h2>Learn from verified outcomes, not from every AI answer.</h2><p>Only a closed case with reviewed feedback can become a lesson. Rejected or reopened cases are revoked immediately, and property facts remain separate from writing-style memory.</p><div class="learning-steps"><div><b>01</b><strong>Close with evidence</strong><span>Staff verifies the real outcome.</span></div><div><b>02</b><strong>Review the lesson</strong><span>Approve or correct reusable wording.</span></div><div><b>03</b><strong>Test improvement</strong><span>Compare before and after outputs.</span></div><div><b>04</b><strong>Reuse or revoke</strong><span>Keep only measured, reviewed value.</span></div></div></section>`);
  const children=[...memory.children].filter(x=>!x.classList.contains('learning-hero'));
  const reviewed=children.at(-1);
  if(reviewed?.tagName==='DETAILS')reviewed.open=false;
  const lab=document.createElement('details');lab.className='learning-lab';lab.open=false;
  lab.innerHTML='<summary>Open the before/after learning lab</summary>';
  children.slice(0,-1).forEach(child=>lab.appendChild(child));
  memory.insertBefore(lab,reviewed);
}

const settings=document.querySelector('[data-page="settings"]');
if(settings){
  const closureCard=document.createElement('section');
  closureCard.className='card';closureCard.dataset.admin='';
  closureCard.innerHTML='<h2>Close after no customer reply</h2><p>Only complaints waiting for the customer are closed automatically. This records an unconfirmed outcome. Customers can reopen with the same Complaint Code. BeLive must be running for scheduled checks.</p><form id="closureForm"><label>Waiting period (days)<input id="closureDays" name="days" type="number" min="1" max="90" required value="7"></label><button type="submit">Save waiting period</button></form><p id="closureStatus" role="status"></p>';
  settings.append(closureCard);
  const groups=[
    {label:'AI & replies',intro:'Test the AI connection, manage automatic replies and edit approved knowledge.',ids:['checkAi','knowledgeForm']},
    {label:'Staff routing',intro:'Choose which team receives a complaint and how long to wait for customer feedback.',ids:['routingForm','closureForm']},
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
  monitor.innerHTML=`<h2>Collect public feedback</h2>
    <button class="primary" id="scanAllSources" type="button" disabled>Collect reviews now</button>
    <p id="scanSummary" role="status"></p>
    <ul id="scanResults" class="scan-results" aria-label="Latest collection results" hidden></ul>
    <details data-admin><summary>Collection schedule</summary><form id="sourceScheduleForm">
      <label>Check every (minutes)<input name="minutes" id="scanInterval" type="number" min="1" max="1440" required value="15"></label>
      <button type="submit">Save interval</button>
    </form></details>`;
  sourcesPage.prepend(monitor);
  const findings=document.createElement('section');
  findings.className='card';
  findings.innerHTML='<h2>Discovered complaints</h2><label>Platform<select id="discoveryPlatform"><option value="">All platforms</option><option value="GOOGLE">Google Reviews</option><option value="FACEBOOK">Facebook</option><option value="THREADS">Threads</option></select></label><div id="discoveryFindings"></div>';
  monitor.after(findings);
  const search=document.createElement('details');
  search.className='card';
  search.innerHTML=`<summary>Record a public complaint</summary>
    <p class="muted">Open a result and confirm it is public. Paste its link and a short summary to create a case for assessment.</p>
    <form id="publicComplaintForm">
      <label>Public review or post URL<input name="public_url" type="url" required maxlength="2000"></label>
      <label>Complaint title<input name="title" required minlength="4" maxlength="120"></label>
      <label>What was reported?<textarea name="description" required minlength="10" maxlength="6000"></textarea></label>
      <p class="form-error error" role="alert"></p>
      <button class="primary" type="submit">Save complaint and assess</button>
    </form>`;
  sourcesPage.append(search);
  findings.before(search);
  const setup = sourcesPage.querySelector('#sourceForm')?.closest('.card');
  if(setup){
    const details = document.createElement('details');
    details.className = 'card';
    details.innerHTML = '<summary>Configure platform sources</summary>';
    setup.before(details);
    while(setup.firstChild)details.append(setup.firstChild);
    setup.remove();
    details.append(document.getElementById('sourcesList'));
  }
}

const newCase=document.getElementById('newCase');
if(newCase)newCase.textContent='＋ Add complaint';
