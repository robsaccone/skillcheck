# Skillcheck: NDA Review

## Show Overview & Script

**Format:** Video/podcast episode — teach, demo, demystify
**Duration:** 45–60 minutes
**Host:** Rob Saccone, NexLaw Partners
**Audience:** Legal professionals, legal ops, legal tech buyers, law firm innovation leaders

---

## The Premise

Six open-source "AI skills" have been published in the last few months claiming to help AI models review NDAs. They come from different sources — Anthropic's official plugins, community repos, indie developers, startup platforms. They range from 130 words to 2,500 tokens.

We built **Skillcheck** — an evaluation harness that puts these skills head-to-head. We wrote a trap-laden NDA with 16 planted issues, created an expert answer key, and ran every skill through five frontier AI models.

The question: **Which skills actually produce the best work product? And how much does the playbook matter versus the model?**

---

## What the Audience Learns

1. What "AI skills" and "plugins" actually are — demystified, with the files shown on screen
2. How to evaluate whether an AI legal tool is doing real analysis or just pattern matching
3. Where current models succeed and fail on a realistic legal review task across different playbooks
4. A framework for building their own evaluations (applicable beyond NDAs)
5. What the "which playbook wins?" question means for firms buying or building legal AI

---

## The Cast of Characters

### The Models

| Model | Provider | Role in the Story |
|-------|----------|-------------------|
| Claude Opus 4.6 | Anthropic | The overachiever — current frontier |
| Claude Sonnet 4.5 | Anthropic | The efficient one — same family, lower cost |
| GPT-4o | OpenAI | The incumbent — everyone's first AI experience |
| Gemini 2.5 Pro | Google | The dark horse |
| Llama 3.3 70B | Meta / open-source | The scrappy underdog — free, runs anywhere |

### The Skills

| Skill | Source | Character |
|-------|--------|-----------|
| `nda_review/baseline` | Skillcheck | The bare prompt — "review this NDA." Raw talent, no playbook. |
| `nda_review/lawvable` | Community open-source | The sticky note — 130 words of guidance |
| `nda_triage/anthropic` | Anthropic (official) | The intake checklist — GREEN/YELLOW/RED |
| `contract_review/anthropic` | Anthropic (official) | The general practitioner — broad, not deep |
| `nda_review/evolsb` | Indie developer | The textbook — CUAD dataset, 2,500 tokens of structured methodology |
| `nda_review/skala` | Startup platform | The founder's friend — startup-focused template comparison |
| `nda_review/custom` | Custom-built | The specialist — 900 words of NDA-specific analysis framework |

### The NDA

A "Mutual Non-Disclosure Agreement" between Acme Technologies and a Recipient. Looks standard. Reads standard. Is absolutely not standard. Sixteen issues hidden across the document, ranging from the obvious ($1,000 liability cap) to the subtle (asymmetric marking requirements for CI definitions, missing residuals clause).

Three tiers:
- **Must-Catch (6 issues):** Miss these and you've committed malpractice
- **Should-Catch (5 issues):** A competent reviewer finds these
- **Nice-to-Catch (5 issues):** Senior associates and partners catch these

---

## Show Script

### COLD OPEN (3 minutes)

*[NDA displayed on screen]*

> "This is a Mutual Non-Disclosure Agreement. I wrote it myself — or rather, I poisoned it myself. There are sixteen issues hidden in this document. Some are obvious. Some are subtle. One of them is genuinely devious.

> I'm going to give this NDA to five AI models and grade their reviews the way I used to grade associates. Some of these models have been given a playbook — what the industry is now calling 'AI skills.' Some are working cold, with nothing but their training.

> This is Skillcheck. Let's see who passes."

---

### SEGMENT 1: THE SETUP (8 minutes)

**Objective:** Teach the audience what skills are. Show, don't tell.

*[Switch to screen share — Skillcheck app, Skill Viewer tab]*

> "Before we look at results, let me show you what we're actually testing. These are AI skills — plain text files that tell a model how to do a job."

*[Show `nda_review/lawvable.skill.md` — 130 words]*

> "This is the simplest one. From an open-source project called Lawvable. Five steps, four things to flag. That's it. Shorter than this paragraph.

> The question: does even this tiny amount of guidance make a measurable difference?"

*[Show `nda_review/evolsb.skill.md` — 2,500 tokens]*

> "Now compare. Built by an indie developer, grounded in an academic dataset called CUAD with 41 risk categories. It asks which party you represent. It considers your negotiating leverage. It produces structured output with specific redline suggestions.

> Same concept — a text file that teaches AI how to do its job. Seven times more detailed."

*[Show the Anthropic skills]*

> "And then there's Anthropic's official contribution — two skills from their open-source legal plugin. One for triage, one for general contract review.

> "Eight skills — from a bare prompt to a 2,500-token methodology. Five models. One rigged NDA. Let's see which playbook wins."

*[Switch to Test Documents & Answer Key tab]*

> "Here's the exam. Sixteen planted issues. Let me walk you through the three that matter most..."

*[Walk through 2-3 key issues:]*

1. The asymmetric CI definition (subtle — the marking requirement difference)
2. The $1,000 liability cap + uncapped indemnification (the risk analysis test)
3. The non-solicitation clause (the scope creep test)

> "That's what a senior attorney would catch. Now let's see what the machines found."

---

### SEGMENT 2: THE RESULTS (25 minutes)

**Objective:** Walk through findings with commentary.

*[Switch to Scorecard tab]*

#### Opening the Scorecard

> "Here's the leaderboard — sorted by weighted score. Must-catch issues worth triple, nice-to-catch worth single."

*[Reveal ranking. Pause.]*

> "A few things jump out..."

*[Narrate based on actual results. Possible threads:]*

- "The best performer was [X] — and it wasn't the most expensive model."
- "Every model caught the $1,000 cap. Easy. The question is what else."
- "The open-source Llama with a good skill scored [higher/lower] than [frontier model] without one."

#### Deep Dive: Side-by-Side

*[Side-by-Side Compare tab]*

**Comparison 1: Same model, best skill vs. bare prompt**

> "Same AI, same NDA — only difference is the playbook. Bare prompt versus the best-performing skill."

*[Walk through issue chips]*

> "Without the skill: [N] issues. With: [N+M]. But look at WHICH issues it gained..."

**Comparison 2: Frontier model vs. open-source with same skill**

> "The money question. [Frontier] versus [Llama + same skill]. One costs dollars per review. One is free."

*[Compare outputs]*

> "Look — [frontier] connected the liability cap to the indemnification. It understood combined risk. [Llama] flagged both separately but missed the relationship. That's the gap between finding issues and understanding risk."

#### Live Fire Round

*[Run Evaluation tab]*

> "Everything so far was pre-run. Let me show you this isn't staged."

*[Select model + skill, click Run, narrate as response appears]*

> "It's pulling the NDA... loading the skill... and here come the results."

*[React to output in real-time]*

> "Caught the asymmetric definition... good, perpetual survival flagged... non-solicitation identified as scope creep, nice... but — it missed the one-way compelled disclosure. That's a should-catch."

*[Auto-scoring chips appear]*

> "Twelve out of sixteen. Let's see how that stacks up."

---

### SEGMENT 3: THE ANALYSIS (10 minutes)

**Objective:** Extract the insights.

#### Skill Comparison

*[Scorecard — Skill Comparison section]*

> "This is the chart I find most interesting. Every skill, every model, side by side. Same NDA, same scoring — which playbook produces the best work product?"

Possible findings:

1. "The best skill wasn't the longest." If the 480-token triage outperforms the 2,500-token textbook on certain models, more instructions can actually hurt.
2. "The bare prompt wasn't as bad as you'd think." If frontier models with no playbook score 75%+, the model already knows a lot — the skill is adding at the margins.
3. "The best skill depends on the model." If evolsb wins on Llama but custom wins on Opus, there's a matching problem — not every playbook works for every associate.
4. "Universal blind spot in [specific issue]." If no skill helps any model find the residuals clause, that's a ceiling for prompt-based approaches.

#### Common Failure Modes

> "Where does AI consistently fail at NDA review, regardless of model or skill?"

- **Connecting provisions across sections.** Flag individually, miss the combined risk.
- **Sins of omission.** Better at spotting bad provisions than noticing absent ones.
- **Calibrating severity.** Everything is "concerning" or everything is equal.
- **Generic vs. actionable.** "This should be negotiated" vs. specific redline language.

#### Expert Scores

> "Automated scoring tells you what the model found. My manual scores tell you whether it understood."

*[Show five dimensions for top performers]*

> "Completeness and precision are table stakes. The dimensions that separate good from great are actionability and judgment."

---

### SEGMENT 4: WHAT THIS MEANS FOR YOU (10 minutes)

**Objective:** Practical takeaways.

#### For Lawyers Evaluating AI Tools

> "When a vendor says their AI reviews contracts — here's how to test the claim. Write a document with known issues. Build an answer key. Run it. Score it.

> When someone says their proprietary AI is better than ChatGPT — make them prove it on YOUR test, not theirs."

#### For Firms Considering Skills/Plugins

> "These skills are free and transparent. You can read every line of instructions the AI receives.

> "The best approach: start with an open-source skill, customize for your firm's playbook — your risk tolerances, your standard positions, your escalation triggers."

#### The Bigger Picture

> "Skills are becoming the way firms encode methodology. The skill IS the playbook, and the AI is the associate following it.

> The firms that build the best playbooks will get the best work product. That's always been true. Now the playbook is executable."

#### Call to Action

> "Everything is open-source — the harness, the test NDA, the answer key, the skills. Skillcheck is designed so you can add your own eval packs. Build one for contract review. Build one for deposition prep. Test your own firm's skills.

> If you do, I'd love to see the results."

---

## Production Notes

### Pre-Recording Checklist
- [ ] All API keys configured and tested
- [ ] All model × skill combinations pre-run (5 models × 8 skills = 40 runs)
- [ ] Results reviewed for interesting findings and narrative threads
- [ ] Manual expert scores entered for top 5-6 performers
- [ ] One "live fire" combination identified (fast model, interesting results)
- [ ] Backup: screenshots of key results in case of API failure during live

### Screen Share Setup
- Skillcheck running full-screen in browser, dark theme
- Practice tab switching — Run → Scorecard → Compare → Skill Viewer flow
- Font sizes legible on screen share

### Audience Q&A Prep
- "Did any model hallucinate issues that weren't there?" (Precision scoring covers this)
- "How do you know your answer key is correct?" (Built it myself, explain methodology)
- "Would this work for [other document type]?" (Yes — add an eval pack)
- "Which model would you actually use in practice?"
- "Are you worried this means less work for associates?"

### Show Notes Links
- Skillcheck repo (if published)
- Lawvable: https://github.com/lawvable/awesome-legal-skills
- Anthropic plugins: https://github.com/anthropics/knowledge-work-plugins
- AgentSkills.legal: https://agentskills.legal
- evolsb: https://github.com/evolsb/claude-legal-skill
- Skala: https://www.skala.io/legal-skills
- Agent Skills spec: https://agentskills.io
- Chad Atlas analysis: https://novehiclesinthepark.substack.com/p/anthropics-open-source-legal-skills

### ROB NOTES

- comment about "vibe lawyering": we're business execs, not lawyers - but that's the point, isn't it?
- 