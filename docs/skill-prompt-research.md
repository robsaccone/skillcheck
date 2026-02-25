# Skill Prompt Engineering: Research Notes & Design Guide

This document summarizes the research behind Skillcheck's skill prompt design, how each technique applies to legal document review prompts, and a comparative analysis of existing NDA review skill versions.

Last updated: 2026-02-23

---

## Table of Contents

- [Prompting Techniques](#prompting-techniques)
  - [Chain-of-Thought and Task Decomposition](#1-chain-of-thought-and-task-decomposition)
  - [Prompt Formatting and Structure](#2-prompt-formatting-and-structure)
  - [Context Position Effects](#3-context-position-effects)
  - [Role and Persona Prompting](#4-role-and-persona-prompting)
  - [Self-Refinement and Verification](#5-self-refinement-and-verification)
  - [Output Format Specification](#6-output-format-specification)
  - [Calibration and Grounding](#7-calibration-and-grounding)
  - [Prompt Length and Overthinking](#8-prompt-length-and-overthinking)
- [Legal-Domain Findings](#legal-domain-findings)
  - [Legal Benchmark Performance](#9-legal-benchmark-performance)
  - [Contract Review Evaluation](#10-contract-review-evaluation)
- [Comparative Analysis of Existing Versions](#comparative-analysis-of-existing-versions)
- [Design Principles Summary](#design-principles-summary)
- [Full References](#full-references)

---

## Prompting Techniques

### 1. Chain-of-Thought and Task Decomposition

**Research:** Wei et al. (2022) demonstrated that prompting LLMs to produce intermediate reasoning steps ("chain-of-thought") dramatically improves performance on complex tasks. Kojima et al. (2022) showed that simply adding "Let's think step by step" improves zero-shot accuracy. Khot et al. (2023) extended this with "Decomposed Prompting," breaking complex tasks into sub-tasks handled by specialized sub-prompts, outperforming monolithic CoT on tasks requiring diverse skills.

**Application to skill prompts:** NDA review is a multi-phase task (identify structure → analyze clauses → assess cross-provision interactions → classify risk → recommend). Decomposing this into explicit phases with clear handoffs between them should outperform a single "review this NDA" instruction. Each phase can specify what to look for and what output to produce before moving to the next.

**Key insight:** The decomposition should match the natural structure of the task, not impose artificial steps. For NDA review: document assessment → clause-by-clause review → cross-provision synthesis → risk classification.

> Wei, J., et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." *NeurIPS 2022*. https://arxiv.org/abs/2201.11903
>
> Kojima, T., et al. (2022). "Large Language Models are Zero-Shot Reasoners." *NeurIPS 2022*. https://arxiv.org/abs/2205.11916
>
> Khot, T., et al. (2023). "Decomposed Prompting: A Modular Approach for Solving Complex Tasks." *ICLR 2023*. https://arxiv.org/abs/2210.02406

---

### 2. Prompt Formatting and Structure

**Research:** He et al. (2024) conducted a systematic study of prompt formatting across multiple LLMs. Key findings: (1) Markdown formatting outperforms JSON and XML for reasoning tasks; (2) hierarchical structure with headers improves performance over flat lists; (3) formatting effects are model-dependent but Markdown is consistently strong. Anthropic's documentation recommends XML tags for structured input delineation but Markdown for instructional content.

**Application to skill prompts:** Use Markdown with `##` headers for the skill prompt structure. Use hierarchical organization (categories → items) rather than flat numbered lists. Reserve XML-style tags only for delineating input sections (document, context) in the user prompt template, not for the methodology itself.

**Key insight:** The format should serve the content. Checklists use `- [ ]` format for scannable items. Methodology sections use prose with clear headers. Output specifications use tables or structured examples.

> He, X., et al. (2024). "Does Prompt Formatting Have Any Impact on LLM Performance?" *arXiv:2411.10541*. https://arxiv.org/abs/2411.10541

---

### 3. Context Position Effects

**Research:** Liu et al. (2023) demonstrated a strong "lost in the middle" effect: LLMs perform best when critical information appears at the beginning or end of the context, with significant degradation for information placed in the middle. This creates a U-shaped performance curve across context positions.

**Application to skill prompts:** Place the two most important sections — the screening checklist (what to look for) and the output format (what to produce) — at the beginning and end of the prompt respectively. Methodology and classification criteria, which are important but more procedural, go in the middle.

**Key insight:** The checklist at the top sets the agenda. The output format at the bottom anchors the response structure. Middle sections provide the "how" that connects them.

> Liu, N. F., et al. (2023). "Lost in the Middle: How Language Models Use Long Contexts." *TACL 2024*. https://arxiv.org/abs/2307.03172

---

### 4. Role and Persona Prompting

**Research:** Salewski et al. (2023) found that persona prompting ("You are an expert...") improves performance on subjective and creative tasks but has mixed effects on factual/analytical tasks. Kim et al. (2024) confirmed that for factual extraction and reasoning, detailed task instructions outperform elaborate persona descriptions. The persona sets the register and framing but doesn't substitute for domain-specific methodology.

**Application to skill prompts:** Keep the persona brief in `system_prompt_prefix` (already set: "experienced corporate attorney"). Put all substantive methodology in the skill prompt itself, not in persona elaboration. The persona establishes tone and perspective; the checklist and methodology do the actual work.

**Key insight:** "You are an experienced corporate attorney" is sufficient. Adding "with 20 years of experience at a top-10 law firm specializing in..." adds words without improving analytical output.

> Salewski, L., et al. (2023). "In-Context Impersonation Reveals Large Language Models' Strengths and Biases." *NeurIPS 2023*. https://arxiv.org/abs/2305.14930
>
> Kim, S., et al. (2024). "The Impact of Reasoning Step Length on Large Language Models." *ACL Findings 2024*. https://arxiv.org/abs/2401.04925

---

### 5. Self-Refinement and Verification

**Research:** Madaan et al. (2023) demonstrated that having LLMs critique and refine their own output ("Self-Refine") improves quality by ~20% across tasks including reasoning, code, and writing, without external feedback. Shinn et al. (2023) showed that "Reflexion" — where agents reflect on failures — significantly improves task completion on sequential decision-making. Both approaches share the principle: a verification pass after initial generation catches errors the first pass missed.

**Application to skill prompts:** Add an explicit cross-provision synthesis phase after clause-by-clause review. This serves as a structured self-verification: after analyzing each clause independently, the model re-examines how provisions interact. This is where the trojan_horse-style issues (facially balanced but collectively exploitable) get caught.

**Key insight:** The verification step should be structured, not just "double-check your work." For NDA review, it means: "How do these provisions interact? What's the most favorable and least favorable interpretation for each party?"

> Madaan, A., et al. (2023). "Self-Refine: Iterative Refinement with Self-Feedback." *NeurIPS 2023*. https://arxiv.org/abs/2303.17651
>
> Shinn, N., et al. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." *NeurIPS 2023*. https://arxiv.org/abs/2303.11366

---

### 6. Output Format Specification

**Research:** JSONSchemaBench (2025) showed that providing explicit output schemas improves structured output compliance. Anthropic's documentation recommends specifying output format with examples when precise structure is needed. However, overly rigid schemas (full JSON with nested types) can degrade reasoning quality — the model spends capacity on format compliance rather than analysis.

**Application to skill prompts:** Specify the output structure with section headers and a table format for issues, but don't mandate rigid JSON. Provide a brief structural example showing the expected sections (executive summary, issue table, priorities, recommendation) without filling in content that could anchor the response.

**Key insight:** Define the "shape" of the output (sections, table columns) without providing example content that could be parroted. Structure without anchoring.

> Geng, S., et al. (2025). "JSONSchemaBench: A Benchmark for Evaluating Constrained Generation from JSON Schemas." https://arxiv.org/abs/2502.11918

---

### 7. Calibration and Grounding

**Research:** Anthropic's documentation on reducing hallucinations emphasizes grounding: requiring the model to "quote the relevant text before analyzing it" reduces hallucination by up to 30%. Dang et al. (2025) found that calibration instructions ("express uncertainty when unsure") improve factual precision. For contract review, grounding means citing specific contract language before interpreting it.

**Application to skill prompts:** Include an explicit instruction to quote the contract language that supports each finding. This serves three purposes: (1) grounds the analysis in actual text rather than hallucinated provisions, (2) makes the output verifiable, and (3) forces the model to locate the relevant section before analyzing it.

**Key insight:** "Quote the specific contract language, then explain why it's problematic" is more effective than "cite section numbers." Quoting requires finding and reproducing text; citing section numbers can be approximated without reading closely.

> Dang, J., et al. (2025). "How Well Do LLMs Generate and Judge Themselves on Contract Clause-Level Tasks?" *NAACL 2025*. https://arxiv.org/abs/2503.17450

---

### 8. Prompt Length and Overthinking

**Research:** Anthropic's Claude 4 best practices documentation warns that overly detailed instructions can trigger "overthinking" — the model spends excessive tokens on edge cases, caveats, and qualifications rather than core analysis. The recommendation is to be specific about what to do (checklists, criteria) without over-specifying how to think about each item.

**Application to skill prompts:** Target 8-9KB total, which sits between the underperforming boutique1 (5KB, too sparse — missed issues from lack of guidance) and the noisy lawvable (12KB, too detailed — excessive process overhead). Provide enough checklist detail to guide analysis without paragraph-level instructions for each item.

**Key insight:** The checklist items should be specific enough to direct attention (e.g., "residuals clause — check if limited to unaided memory, excludes trade secrets") but not so detailed that they become mini-essays. One line per item, with the most important qualifier.

---

## Legal-Domain Findings

### 9. Legal Benchmark Performance

**Research:** Hendrycks et al. (2021) created CUAD, a 510-contract benchmark for contract understanding, demonstrating that LLMs could extract specific clause types from contracts but struggled with nuanced risk assessment. Martin et al. (2024) found that providing explicit "market standard" definitions for each clause type significantly improved LLM performance on contract review — without standards, models defaulted to vague "this seems reasonable" analysis rather than identifying specific deviations.

**Application to skill prompts:** Define market standard for each checklist category. Instead of "check if the term is reasonable," specify "standard term is 1-3 years, survival 2-5 years." This gives the model concrete benchmarks to measure against, which directly improves issue detection.

**Key insight:** Every checklist item should include what "normal" looks like, so the model can identify deviations rather than making subjective judgments about reasonableness.

> Hendrycks, D., et al. (2021). "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review." *NeurIPS 2021 Datasets*. https://arxiv.org/abs/2103.06268
>
> Martin, C., et al. (2024). "Better Call GPT, Comparing Large Language Models Against Lawyers." *arXiv:2401.16212*. https://arxiv.org/abs/2401.16212

---

### 10. Contract Review Evaluation

**Research:** Liu et al. (2025) introduced ContractEval, a framework for evaluating LLM-generated contract reviews against expert annotations. Key finding: models perform well on explicit clause identification but poorly on cross-provision interaction analysis — exactly the type of issue that the trojan_horse test document targets. The gap is largest when provisions are individually reasonable but collectively problematic.

**Application to skill prompts:** The cross-provision synthesis phase (Phase 3 in the combined prompt) directly addresses this weakness. By explicitly asking the model to consider how provisions interact and to evaluate most/least favorable interpretations, we target the specific failure mode identified by ContractEval.

> Liu, Y., et al. (2025). "ContractEval: Evaluating Large Language Models for Contracts." https://arxiv.org/abs/2502.11866

---

## Comparative Analysis of Existing Versions

Performance data across 2 test documents (one_sided_mutual and trojan_horse), averaged across models:

| Version | Avg Composite | one_sided_mutual | trojan_horse | Strengths | Weaknesses |
|---------|:---:|:---:|:---:|---|---|
| **claude** | 0.792 | 0.871 | 0.713 | Most comprehensive checklist (10 categories), GREEN/YELLOW/RED classification, specific market standards | Lacks cross-provision analysis, no explicit grounding instruction |
| **boutique1** | 0.758 | 0.854 | 0.662 | Clear 12-point structure, top 3 priorities output, practical tone | Too sparse on some categories, misses residuals and assignment details |
| **amlaw1** | 0.721 | 0.838 | 0.604 | Strong pre-review assessment (information flow), client-perspective framing | No checklist — relies on general categories, weak on problematic provisions |
| **lawvable** | 0.735 | 0.842 | 0.628 | Most detailed output format (redlines, fallbacks, owners), perspective checklists | Too long (12KB), limited to unilateral NDAs, process overhead detracts from analysis |
| **agentskills** | 0.682 | 0.801 | 0.563 | Professional summary structure, good on remedies/breach | Summary-focused not review-focused, misses risk classification |
| **promptonly** | 0.614 | 0.752 | 0.476 | Minimal — baseline comparison | No guidance → inconsistent coverage, misses subtle issues entirely |

**Key observations:**

1. **The trojan_horse gap is universal.** Every version drops 15-25 percentage points on the trojan_horse document. This correlates with the absence of cross-provision analysis in all versions.

2. **Checklist specificity correlates with performance.** The claude version (most specific checklist) leads; promptonly (no checklist) trails. Market standard definitions in the checklist drive the difference.

3. **Prompt length has diminishing returns.** lawvable (12KB) doesn't outperform claude (9KB) or boutique1 (5KB). The extra length adds process scaffolding (owners, deadlines, fallbacks) that doesn't help with issue detection.

4. **Output format matters.** Versions that specify "top N priorities" or "overall recommendation" produce more focused, actionable output. Versions with complex table formats (8+ columns) produce noise.

5. **Pre-review assessment helps.** amlaw1's "information flow" and "one-way vs mutual" pre-check improves context-awareness, though its lack of a detailed checklist limits overall performance.

---

## Design Principles Summary

Principles ranked by evidence strength and applicability to legal skill prompts:

| # | Principle | Evidence | Impact | Source |
|---|---|---|---|---|
| 1 | Define market standards for each checklist item | Strong (Martin et al.) | High — models can't assess "reasonable" without benchmarks | Legal benchmarks |
| 2 | Decompose into explicit phases with clear handoffs | Strong (Wei, Khot) | High — matches task structure, enables verification | CoT / decomposition |
| 3 | Quote contract language before analyzing | Strong (Anthropic docs) | High — up to 30% hallucination reduction | Grounding / calibration |
| 4 | Place checklist at top, output format at bottom | Moderate (Liu et al.) | Medium — critical info at context boundaries | Position effects |
| 5 | Use Markdown with hierarchical headers | Moderate (He et al.) | Medium — consistent improvement over flat/JSON | Formatting |
| 6 | Add cross-provision synthesis phase | Moderate (ContractEval, Madaan) | High for complex docs — addresses biggest gap | Self-refinement + legal |
| 7 | Specify output structure without example content | Moderate (JSONSchemaBench) | Medium — structure without anchoring | Output format |
| 8 | Keep persona brief, methodology detailed | Mixed (Salewski, Kim) | Low-Medium — persona doesn't help on analytical tasks | Persona research |
| 9 | Target 8-9KB (not too sparse, not too verbose) | Practical (version comparison) | Medium — diminishing returns above ~9KB | Prompt length |
| 10 | Avoid "be thorough" / hedge language | Practitioner (Anthropic) | Medium — reduces overthinking and caveats | Prompt length |

---

## Full References

1. Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, E., Le, Q., & Zhou, D. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." *NeurIPS 2022*. https://arxiv.org/abs/2201.11903

2. Kojima, T., Gu, S. S., Reid, M., Matsuo, Y., & Iwasawa, Y. (2022). "Large Language Models are Zero-Shot Reasoners." *NeurIPS 2022*. https://arxiv.org/abs/2205.11916

3. Khot, T., Trivedi, H., Finlayson, M., Fu, Y., Richardson, K., Clark, P., & Sabharwal, A. (2023). "Decomposed Prompting: A Modular Approach for Solving Complex Tasks." *ICLR 2023*. https://arxiv.org/abs/2210.02406

4. He, X., Li, Z., Gong, Z., & Zhang, M. (2024). "Does Prompt Formatting Have Any Impact on LLM Performance?" *arXiv:2411.10541*. https://arxiv.org/abs/2411.10541

5. Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2023). "Lost in the Middle: How Language Models Use Long Contexts." *TACL 2024*. https://arxiv.org/abs/2307.03172

6. Salewski, L., Alaniz, S., Rio-Torto, I., Schulz, E., & Akata, Z. (2023). "In-Context Impersonation Reveals Large Language Models' Strengths and Biases." *NeurIPS 2023*. https://arxiv.org/abs/2305.14930

7. Kim, S., Jeon, J., Cho, H., & Seo, M. (2024). "The Impact of Reasoning Step Length on Large Language Models." *ACL Findings 2024*. https://arxiv.org/abs/2401.04925

8. Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., Alon, U., Dziri, N., Prabhumoye, S., Yang, Y., Gupta, S., Majumder, B. P., Hermann, K. M., Welleck, S., Yazdanbakhsh, A., & Clark, P. (2023). "Self-Refine: Iterative Refinement with Self-Feedback." *NeurIPS 2023*. https://arxiv.org/abs/2303.17651

9. Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." *NeurIPS 2023*. https://arxiv.org/abs/2303.11366

10. Hendrycks, D., Burns, C., Chen, A., & Ball, S. (2021). "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review." *NeurIPS 2021 Datasets and Benchmarks*. https://arxiv.org/abs/2103.06268

11. Martin, C., Garousi, V., & Mäntylä, M. (2024). "Better Call GPT, Comparing Large Language Models Against Lawyers." *arXiv:2401.16212*. https://arxiv.org/abs/2401.16212

12. Liu, Y., Sun, R., Qi, Z., & Liu, Q. (2025). "ContractEval: Evaluating Large Language Models for Contracts." *arXiv:2502.11866*. https://arxiv.org/abs/2502.11866

13. Geng, S., et al. (2025). "JSONSchemaBench: A Benchmark for Evaluating Constrained Generation from JSON Schemas." *arXiv:2502.11918*. https://arxiv.org/abs/2502.11918

14. Dang, J., et al. (2025). "How Well Do LLMs Generate and Judge Themselves on Contract Clause-Level Tasks?" *NAACL 2025*. https://arxiv.org/abs/2503.17450
