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
    <h2>Customer support</h2>
    <div class="entry-lanes">
      <article class="entry-lane">
        <h3>Public reviews</h3>
        <p>Review reports collected from public sources and prepare replies for staff review.</p>
        <div class="lane-status" id="proactiveSummary"></div>
        <div class="lane-actions"><button class="primary" data-go="sources">Open public reviews</button></div>
      </article>
      <article class="entry-lane">
        <h3>Customer Support</h3>
        <p>Open the queue to review replies or take ownership of a case.</p>
        <div class="lane-status" id="reactiveSummary"></div>
        <div class="lane-actions"><button class="primary" data-go="cases">Open Customer Support</button></div>
      </article>
    </div>
  </section>
  <div class="metrics" id="metrics"></div>
  <div class="command-grid">
    <div>
      <section class="card"><div class="card-heading"><div><h2>Unified support queue</h2><p>Public reports and customer support cases appear together.</p></div></div><div class="table-scroll"><table><thead><tr><th>Case</th><th>Urgency</th><th>Status</th><th>Owner</th><th>Next action / deadline</th></tr></thead><tbody id="recentCases"></tbody></table></div></section>
      <section class="card"><h2>Automatic support</h2><p id="routineSummary"></p></section>
    </div>
    <aside>
      <section class="card attention-card"><h2>Needs a person</h2><div id="attention"></div></section>
      <section class="card learning-pulse"><span class="eyebrow">SELF-LEARNING</span><strong id="learningCount">0</strong><h2>Reviewed lessons ready</h2><p id="learningSummary">Verified outcomes become reusable guidance only after review.</p></section>
    </aside>
  </div>`;

const settings=document.querySelector('[data-page="settings"]');
if(settings){
  const closureCard=document.createElement('section');
  closureCard.className='card';closureCard.dataset.admin='';
  closureCard.innerHTML='<h2>Close after no customer reply</h2><p>Only complaints waiting for the customer are closed automatically. This records an unconfirmed outcome. Customers can reopen from Track complaint. BeLive must be running for scheduled checks.</p><form id="closureForm"><label>Waiting period (days)<input id="closureDays" name="days" type="number" min="1" max="90" required value="7"></label><button type="submit">Save waiting period</button></form><p id="closureStatus" role="status"></p>';
  settings.append(closureCard);
  const groups=[
    {label:'AI & replies',intro:'Test the AI connection, manage automatic replies and edit approved knowledge.',ids:['checkAi','knowledgeForm']},
    {label:'Staff routing',intro:'Choose which team receives a complaint and how long to wait for customer feedback.',ids:['routingForm','closureForm']},
    {label:'Properties & tenants',intro:'Manage verified property and tenant records. Customers can submit and track complaints without a tenant account.',ids:['condoForm','tenantForm','recordForm','resources']},
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

}

const sourceHeading=document.querySelector('[data-page="sources"] h2');
if(sourceHeading)sourceHeading.textContent='Proactive complaint discovery';
const sourceIntro=document.querySelector('[data-page="sources"] h2 + p');
if(sourceIntro)sourceIntro.textContent='Connect the public sources you are allowed to read. Choose how many recent days each API source covers. Facebook collects comments under Page posts; Threads follows replies on your connected account’s posts. Google API collection needs authorised Business Profile access. Scheduled checks run while BeLive is running.';
const sourcesPage=document.querySelector('[data-page="sources"]');
if(sourcesPage){
  const monitor=document.createElement('section');
  monitor.className='card';
  monitor.innerHTML=`<h2>Collect public feedback</h2>
    <button class="primary" id="scanAllSources" type="button" disabled>Collect feedback now</button>
    <p id="scanSummary" role="status"></p>
    <ul id="scanResults" class="scan-results" aria-label="Latest collection results" hidden></ul>
    <details data-admin><summary>Collection schedule</summary><form id="sourceScheduleForm">
      <label>Check every (minutes)<input name="minutes" id="scanInterval" type="number" min="1" max="1440" required value="15"></label>
      <button type="submit">Save interval</button>
    </form></details>`;
  const importer=document.createElement('section');
  importer.className='card';
  importer.innerHTML=`<h2>Import a Google review from a link</h2>
    <p>Copy the link from <strong>Share</strong> on the individual review. BeLive saves the visible review as a case and starts assessment.</p>
    <form id="reviewImportForm">
      <label>Google review link<input name="url" type="url" placeholder="https://maps.app.goo.gl/…" required maxlength="2000"></label>
      <button type="submit" class="primary">Import review</button>
    </form>
    <p id="reviewImportStatus" role="status"></p>`;
  const apiScans=document.createElement('details');
  apiScans.className='card';
  apiScans.innerHTML='<summary>Scheduled collection with API access</summary>';
  apiScans.append(monitor);
  const batch=document.createElement('section');
  batch.className='card';
  batch.innerHTML=`<h2>Collect Google reviews</h2>
    <p>Read up to 10 written 1–2 star reviews. Already saved reviews are skipped.</p>
    <form id="reviewBatchForm"><label>Google Maps listing link<textarea name="links" rows="2" required maxlength="20010">https://www.google.com/maps/place/BeLive+Co-Living/@3.0787464,101.5791608,17z/data=!4m8!3m7!1s0x20321faf2201617f:0xc39a6196edc53b7d!8m2!3d3.0787464!4d101.5791608!9m1!1b1!16s%2Fg%2F11vqnn65b7?entry=ttu</textarea></label>
    <p class="muted">You can also paste individual review links, one per line.</p>
    <button class="primary" type="submit">Collect up to 10 reviews</button></form>
    <button type="button" id="reviewChromeSignIn" class="text-button" data-admin>Google sign-in for collector</button>
    <p id="reviewBatchStatus" role="status"></p><div class="case-actions" id="reviewBatchResults"></div>`;
  sourcesPage.prepend(batch,importer,apiScans);
  const findings=document.createElement('section');
  findings.className='card';
  findings.innerHTML='<h2>Discovered complaints</h2><label>Platform<select id="discoveryPlatform"><option value="">All platforms</option><option value="GOOGLE">Google Reviews</option><option value="FACEBOOK">Facebook</option><option value="THREADS">Threads</option></select></label><div id="discoveryFindings"></div>';
  apiScans.after(findings);
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
