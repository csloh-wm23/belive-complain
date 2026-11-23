# Native Hermes is the Agent; GPT is its model

The production default is `BELIVE_AGENT_ENGINE=hermes`. OpenAI/GPT remains the provider/model. Official NousResearch `run_agent.AIAgent` executes each role and tool loop; BeLive owns the interface, source records, case state, authorisation and delivery safeguards. Model names never switch the engine to a direct API silently. The explicit `direct` setting is a labelled legacy transport for regression testing, not a missing-runtime fallback.

## Installation and startup

On another Windows computer, retain your own `.env`, database, company documents and recovery key. Install Git for Windows and Python, run **Install Hermes Agent.bat** once, then **Run BeLive Prototype.bat**. The installer checks out official `NousResearch/hermes-agent` release **v0.23.3**, installs its locked core dependencies with Python 3.14, and verifies real `AIAgent` and `MemoryStore` imports. It does not install Ubuntu or computer-control/browser extras. Existing modified runtime files are preserved rather than reset. Runtime locations are recorded in ignored `data/hermes-runtime.json`; dependencies and private Agent profiles do not enter GitHub.

`BELIVE_HERMES_PYTHON` can explicitly select an existing Hermes environment. An unavailable native runtime fails closed; the launcher tells the operator to install it, and the application does not silently call GPT directly.

## What runs through native Hermes

Complaint assessment and responses, contextual WhatsApp replies, SOP selection, photo analysis, safety review, feedback learning and approved-experience comparisons use native `AIAgent` conversations. Decisions-only direct classification is disabled in native mode. WhatsApp replies call `read_current_support_evidence` to obtain the current selected SOP, approved experience and verified staff instructions. Research uses native Hermes to invoke the bounded `search_official_support` tool and summarise its cited results. That tool uses the configured OpenAI web-search transport; OpenAI remains a model/tool provider, not a replacement for the Agent.

Only explicitly registered BeLive tools are exposed. The Agent cannot acquire terminal, arbitrary file-system or messaging tools. Sending messages and changing complaint/staff state remain validated application operations after Agent output review.

## Memory and customer isolation

Canonical approved company knowledge remains in BeLive's versioned records and encrypted push/download backup. It is retrieved by the Agent's evidence tool. Approved writing guidance is projected into official Hermes `MemoryStore`; rejections revoke the projection on the next request. Customer follow-up analysis proposes learning for review rather than automatically publishing private or unverified content.

WhatsApp threads use separate hashed native profiles, and each run receives only its current conversation/evidence. Default context files are disabled, while official Hermes memory loading remains enabled in the isolated profile. The worker checks that the native Agent loaded exactly the current approved MemoryStore projection; withdrawn entries are removed before generation. Raw provider keys travel to the subprocess through stdin, never command arguments, status responses or execution records.

## Verify the engine

Open **System setup → AI & replies → Test AI connection**. The status states the Agent engine separately from the GPT model. **Native Hermes execution evidence** lists the official class, release/commit, role, real model-call count and executed tool names. A WhatsApp output also records the native execution IDs and tools that produced its reply. A memory-only operation with zero model calls is not proof of an inference run.

This engine check is separate from WhatsApp connectivity. A website `wa.me` link, an installed Agent or a successful simulated conversation does not authorise the company number. Retaining the phone Business app still requires Meta-supported coexistence onboarding and a reachable production webhook.

Official sources: [Windows installation](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native), [Hermes Agent source](https://github.com/NousResearch/hermes-agent).
