# LLM-as-Judge: Research Notes & Implementation Guide

This document summarizes the research behind Skillcheck's LLM-as-Judge scoring system, how each technique is implemented, and opportunities for future improvement.

Last updated: 2026-02-22

---

## Table of Contents

- [Implemented Techniques](#implemented-techniques)
  - [Chain-of-Thought Reasoning (G-Eval)](#1-chain-of-thought-reasoning-g-eval)
  - [Binary Scales & Few-Shot Calibration](#2-binary-scales--few-shot-calibration)
  - [Anti-Verbosity Instruction](#3-anti-verbosity-instruction)
  - [Panel of LLM Evaluators (PoLL)](#4-panel-of-llm-evaluators-poll)
  - [Self-Enhancement Bias Detection](#5-self-enhancement-bias-detection)
- [How It All Fits Together](#how-it-all-fits-together)
- [Known Gaps & Future Directions](#known-gaps--future-directions)
  - [Expert Calibration](#1-expert-calibration)
  - [Pairwise Evaluation](#2-pairwise-evaluation)
  - [Agreeableness Bias](#3-agreeableness-bias)
  - [Multi-Agent Deliberation](#4-multi-agent-deliberation)
  - [Minority-Veto Ensemble](#5-minority-veto-ensemble)
  - [Regression-Based Calibration](#6-regression-based-calibration)
  - [Broader Bias Coverage](#7-broader-bias-coverage)
  - [False Positive Traps](#8-false-positive-traps-in-answer-keys)
- [Research Validity](#research-validity)
- [Full References](#full-references)

---

## Implemented Techniques

### 1. Chain-of-Thought Reasoning (G-Eval)

**Research:** G-Eval (Liu et al., 2023) demonstrated that having an LLM evaluator reason step-by-step before assigning scores significantly improves correlation with human judgments. The method uses a "form-filling paradigm" where the model produces structured reasoning before each score. On summarization benchmarks, G-Eval with GPT-4 achieved a Spearman correlation of 0.514 with human judgments, substantially outperforming prior automated metrics.

**Our implementation** (`judge.py`, prompt lines 88-89):
- The judge prompt instructs: "For each issue, FIRST write a brief reasoning explanation, THEN assign a score."
- Output format nests reasoning with each detection: `{"ISSUE-01": {"detected": 1, "reasoning": "..."}}`
- `_normalize_issues()` (lines 153-170) handles both the new nested format and legacy flat format for backward compatibility.

**Assessment:** Correctly applied. The core G-Eval insight (reason before scoring) is preserved. Our implementation is pointwise rather than G-Eval's original form-filling with probability weighting, but the reasoning-first principle is what matters most.

> Liu, Y., et al. (2023). "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment." https://arxiv.org/abs/2303.16634

---

### 2. Binary Scales & Few-Shot Calibration

**Research:** Husain (2024) argues that binary pass/fail judgments are the most reliable and reproducible LLM evaluation scale. Multi-point scales (1-5 Likert) suffer from inconsistent interpretation across evaluators. He recommends "critique shadowing" — having domain experts provide detailed critiques alongside judgments — and iterating the judge prompt against expert examples until achieving >90% agreement.

Eugene Yan's practitioner guide (2024) independently confirms: binary scales enable classification metrics (precision, recall) which are more actionable than correlation metrics (Spearman, Kendall) used with continuous scales.

**Our implementation** (`judge.py`, prompt lines 63-73):
- Per-issue scoring is strictly binary: 0 (missed) or 1 (detected).
- The prompt includes calibration examples defining exactly what each score means:
  - **Score 1 (detected):** "The model explicitly names or substantively discusses the concern, even using different terminology."
  - **Score 0 (missed):** "The issue is not mentioned at all, or only tangentially referenced without substantive analysis."

**Assessment:** Binary scale correctly applied. Calibration examples are present but minimal (one example each for 0 and 1). Husain's highest-impact recommendation — iterating against expert judgments — has not been done yet (see [Expert Calibration](#1-expert-calibration) below).

> Husain, H. (2024). "Your AI Product Needs Evals." https://hamel.dev/blog/posts/llm-judge/
>
> Yan, E. (2024). "Evaluating the Effectiveness of LLM-Evaluators." https://eugeneyan.com/writing/llm-evaluators/

---

### 3. Anti-Verbosity Instruction

**Research:** Zheng et al. (2024) identified three systematic biases in LLM judges: position bias (favoring the first or last response), verbosity bias (favoring longer responses regardless of substance), and self-enhancement bias. Verbosity bias causes judges to inflate scores for longer responses even when the additional length adds no analytical value.

**Our implementation** (`judge.py`, prompt lines 80-84):
- A dedicated prompt section titled "Important: Avoid Verbosity Bias" instructs: "Do NOT give credit for length. A concise response that identifies an issue in one sentence scores the same as a verbose response that takes a paragraph. Penalize responses that pad length without adding analytical substance."
- The closing instruction reinforces: "Score based on substance, not formatting or length."

**Assessment:** Reasonable application, though research suggests prompt-level instructions are a **weak mitigation** for verbosity bias — the tendency is somewhat baked into model training. More effective mitigations include pairwise comparison (which controls for length by comparing directly) or regression-based post-hoc calibration.

> Zheng, L., et al. (2024). "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." https://arxiv.org/abs/2306.05685

---

### 4. Panel of LLM Evaluators (PoLL)

**Research:** Verga et al. (2024) showed that a panel of smaller, diverse-family models outperforms a single large judge model across multiple benchmarks and evaluation settings, while costing 7x less. The key insight is that **diversity across model families** matters more than individual model capability. Using models from different training pipelines reduces correlated biases.

**Our implementation:**
- `judge_panel()` (`judge.py`, lines 403-546) runs multiple judges in parallel via `ThreadPoolExecutor`.
- **Aggregation strategy:**
  - Per-issue binary scores: majority vote (ties go positive — benefit of the doubt)
  - Recommendation match: majority vote
  - False positives: union of unique items, averaged count
  - Composite score: average of individual composites
  - Reasoning: concatenated from all judges with attribution
- `engine.py` wires panel support through `run_evaluation()` and `judge_saved_results()`, dispatching to `judge_panel()` when multiple `judge_model_keys` are provided.
- `pages/evaluate.py` extracts both judge selections from session state and shows panel status.

**Assessment:** Correctly applied in principle. **Notable limitation:** Our panel supports only 2 judges, which means "majority vote" is effectively "either says yes." With 2 judges, ties always resolve positive, biasing toward higher recall at the cost of precision. The original PoLL paper uses larger panels where majority vote is more meaningful. Adding a 3rd judge from a different family (e.g., Gemini alongside Claude + GPT) would make the aggregation more robust.

> Verga, P., et al. (2024). "Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models." https://arxiv.org/abs/2404.18796

---

### 5. Self-Enhancement Bias Detection

**Research:** Wataoka et al. (2024) demonstrated that LLMs assign higher scores to outputs with lower perplexity — meaning they favor text patterns that are familiar to them, which correlates with same-family outputs. The bias mechanism is perplexity-based familiarity rather than explicit self-recognition.

**Our implementation** (`judge.py`, lines 282-305):
- `detect_self_enhancement_risk()` checks if the judge and evaluated model share a provider (e.g., both Anthropic, both OpenAI).
- Returns a warning string when same-family usage is detected.
- Warning is displayed in the result detail view (`pages/result_detail.py`, lines 38-46) and on the judges page (`pages/judges.py`, lines 57-65).
- The judges page recommends cross-family panels when same-family judges are selected.

**Assessment:** Correctly applied as a **detection and warning mechanism**. Note: the "~15% inflation" figure in the warning message is an approximation — the original paper describes the effect as "significant" without quantifying a specific percentage. Our detection is provider-level only and does not account for preference leakage from shared training data across providers.

> Wataoka, K., et al. (2024). "Self-Preference Bias in LLM-as-a-Judge." https://arxiv.org/abs/2410.21819

---

## How It All Fits Together

The judging pipeline flows as follows:

```
Answer Key + Document + Model Response
        │
        ▼
┌─────────────────────────────┐
│  build_judge_prompt()       │  Constructs system + user prompt
│  - CoT instruction          │  with all research-backed techniques
│  - Calibration examples     │  baked into the system prompt
│  - Anti-verbosity warning   │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  judge_response()           │  Single judge: call model, parse
│  OR judge_panel()           │  Panel: parallel calls, aggregate
│  - _normalize_issues()      │  via majority vote
│  - compute_composite_scores │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Result JSON                │
│  - Per-issue detection + reasoning
│  - Recommendation match + reasoning
│  - False positive count + list
│  - Composite score (0.0-1.0)
│  - Panel metadata (if panel)
│  - Self-enhancement warning (if applicable)
└─────────────────────────────┘
```

**Scoring formula:**
```
composite = weighted_hit_rate + recommendation_bonus - fp_penalty
```
- `weighted_hit_rate`: 0-100, severity-weighted (H=3x, M=2x, L=1x)
- `recommendation_bonus`: +10 points for correct sign/negotiate/don't-sign
- `fp_penalty`: -3 points per false positive
- Clamped to [0, 100], stored as 0.0-1.0

---

## Known Gaps & Future Directions

### 1. Expert Calibration

**Priority: HIGH | Effort: MEDIUM**

Husain's most impactful recommendation — and the one we haven't implemented. The process:

1. Score ~5 model responses per test document by hand (human expert judgment).
2. Run the same responses through the judge.
3. Compare per-issue agreement. Target: >90%.
4. Where they disagree, examine why and refine the judge prompt or rubrics.
5. Repeat until convergence.

This is the single most effective way to improve judge accuracy. Everything else is optimization on top of validated baseline accuracy.

> Husain, H. (2024). https://hamel.dev/blog/posts/llm-judge/

---

### 2. Pairwise Evaluation

**Priority: MEDIUM | Effort: MEDIUM**

Research now shows that for subjective assessments, **pairwise comparison** ("Is response A better than B?") produces more stable results than pointwise scoring ("Rate this response"). Our system is entirely pointwise.

For model-vs-model comparison — which is a core use case — a pairwise judge mode would be more reliable than comparing absolute scores that may not be consistently calibrated across runs.

**Implementation sketch:** A new `judge_pairwise()` function that takes two responses and the answer key, asks the judge which response is better and why, and returns a preference with reasoning.

> Zheng, L., et al. (2024). https://arxiv.org/abs/2306.05685
>
> Yan, E. (2024). https://eugeneyan.com/writing/llm-evaluators/

---

### 3. Agreeableness Bias

**Priority: MEDIUM | Effort: LOW**

A newly identified bias (NUS, 2025): LLM judges tend to **agree with the response they're evaluating** rather than critically assessing it against the answer key. This is distinct from verbosity or self-preference bias. The judge may accept a model's framing of an issue even when it doesn't match the rubric.

**Potential mitigation:** Add an explicit instruction to the judge prompt: "Evaluate strictly against the answer key rubric. Do not accept the model's framing if it diverges from the rubric's specific concern, even if the model's point is valid in isolation."

> "Beyond Consensus: Mitigating the Agreeableness Bias in LLM Judge Evaluations." (NUS, 2025). https://aicet.comp.nus.edu.sg/wp-content/uploads/2025/10/Beyond-Consensus-Mitigating-the-agreeableness-bias-in-LLM-judge-evaluations.pdf

---

### 4. Multi-Agent Deliberation

**Priority: MEDIUM | Effort: HIGH**

Beyond independent panel voting, newer approaches have judges **discuss and debate** before reaching a verdict. MAJ-Eval uses persona-based multi-agent debate to achieve substantially higher human alignment (Spearman rho up to 0.47 vs 0.15-0.36 for standard single-agent baselines).

Our current panel runs judges independently and aggregates mechanically. A deliberation step — where judges see each other's reasoning and can revise — could improve quality, especially on ambiguous issues.

**Trade-off:** Significantly more API calls and latency. May be worth offering as an optional "deep evaluation" mode.

> "LLMs-as-Judges: A Comprehensive Survey on LLM-based Evaluation Methods." (2024). https://arxiv.org/abs/2412.05579

---

### 5. Minority-Veto Ensemble

**Priority: LOW-MEDIUM | Effort: LOW**

Instead of majority vote, a **minority-veto** approach (if any judge flags an issue, it's flagged) significantly improves true negative rates. This is particularly relevant for false positive detection: if one judge says a model's flagged issue is actually standard practice, that dissenting signal may be more valuable than a majority vote.

**Implementation:** Change `judge_panel()` aggregation for `false_positives` from union+average to minority-veto (any judge calling FP → FP stands).

> "Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge." (IBM Research, ICLR 2025). https://research.ibm.com/publications/justice-or-prejudice-quantifying-biases-in-llm-as-a-judge

---

### 6. Regression-Based Calibration

**Priority: MEDIUM | Effort: MEDIUM**

Using just 5 human-annotated examples per task to calibrate judge scores via simple regression **halves the maximum prediction error** compared to raw ensemble output. This is a lightweight, high-impact post-processing step.

**Implementation sketch:** After expert calibration (gap #1), fit a simple linear correction: `calibrated_score = a * raw_score + b` using the human-vs-judge comparison data. Apply as a post-processing step in `compute_composite_scores()`.

> "Evaluating Scoring Bias in LLM-as-a-Judge." (2025). https://arxiv.org/html/2506.22316v1

---

### 7. Broader Bias Coverage

**Priority: LOW | Effort: VARIES**

IBM's CALM framework identifies **12 distinct biases** in LLM judges. We currently address only 2 (verbosity, self-preference). Other relevant biases include:

- **Position bias** — judges favor issues presented earlier or later in the prompt. Mitigation: randomize issue order in answer keys.
- **Authority bias** — judges defer to confident-sounding responses. Mitigation: prompt instruction to ignore tone.
- **Preference leakage** — training data overlap between judge and evaluated model inflates scores beyond same-provider effects. Mitigation: harder to detect; cross-family panels help.

> "Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge." (IBM Research, ICLR 2025). https://llm-judge-bias.github.io/

---

### 8. False Positive Traps in Answer Keys

**Priority: LOW | Effort: LOW**

Currently only `vanilla_mutual.json` includes `false_positive_traps` — provisions that are standard but might be incorrectly flagged. The judge prompt references these as optional ("if provided"), but having them in all answer keys would improve false positive detection accuracy for `one_sided_mutual` and `trojan_horse` as well.

---

## Research Validity

The core techniques (G-Eval, PoLL, binary scales) are from 2023-2024 but have been **validated by two comprehensive surveys in late 2024** and remain best practice as of early 2026. The field has expanded rather than contradicted these foundations:

| Technique | Original Paper | Validated By | Status |
|-----------|---------------|--------------|--------|
| Chain-of-thought reasoning | G-Eval (2023) | Both 2024 surveys, Yan (2024) | Best practice |
| Binary per-issue scales | Husain (2024) | Yan (2024), survey consensus | Best practice |
| Panel/ensemble judging | PoLL (2024) | SE-Jury (2025), survey consensus | Best practice, being extended |
| Anti-verbosity instruction | Zheng et al. (2024) | Reproduced widely | Weak mitigation alone; combine with other techniques |
| Self-enhancement detection | Wataoka et al. (2024) | CALM framework (2025) | Valid; broader bias framework now available |

**Key newer developments** (2025-2026) extend rather than replace the foundations:
- Multi-agent deliberation improves on independent panels
- Pairwise evaluation improves on pointwise for model comparison
- Agreeableness bias is a newly identified concern
- Regression calibration provides a lightweight accuracy boost
- Systematic bias frameworks (CALM) provide broader coverage

---

## Full References

1. Liu, Y., Iter, D., Xu, Y., Wang, S., Xu, R., & Zhu, C. (2023). "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment." *arXiv:2303.16634*. https://arxiv.org/abs/2303.16634

2. Verga, P., Hofstätter, S., Althammer, S., Golber, Y., Sciavolino, C., & Hajishirzi, H. (2024). "Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models." *arXiv:2404.18796*. https://arxiv.org/abs/2404.18796

3. Wataoka, K., Hori, T., Baba, Y., & Kashima, H. (2024). "Self-Preference Bias in LLM-as-a-Judge." *arXiv:2410.21819*. https://arxiv.org/abs/2410.21819

4. Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., Zhang, H., Gonzalez, J. E., & Stoica, I. (2024). "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." *NeurIPS 2024*. https://arxiv.org/abs/2306.05685

5. Husain, H. (2024). "Your AI Product Needs Evals." https://hamel.dev/blog/posts/llm-judge/

6. Yan, E. (2024). "Evaluating the Effectiveness of LLM-Evaluators (aka LLM-as-Judge)." https://eugeneyan.com/writing/llm-evaluators/

7. Shankar, S., et al. (2024). "A Survey on LLM-as-a-Judge." *arXiv:2411.15594*. https://arxiv.org/abs/2411.15594

8. Chen, H., et al. (2024). "LLMs-as-Judges: A Comprehensive Survey on LLM-based Evaluation Methods." *arXiv:2412.05579*. https://arxiv.org/abs/2412.05579

9. "Beyond Consensus: Mitigating the Agreeableness Bias in LLM Judge Evaluations." (NUS, 2025). https://aicet.comp.nus.edu.sg/wp-content/uploads/2025/10/Beyond-Consensus-Mitigating-the-agreeableness-bias-in-LLM-judge-evaluations.pdf

10. "Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge." (IBM Research, ICLR 2025). https://arxiv.org/abs/2410.02736

11. "Evaluating Scoring Bias in LLM-as-a-Judge." (2025). https://arxiv.org/abs/2506.22316

12. "SE-Jury: An LLM-as-Ensemble-Judge Metric for Narrowing the Gap with Human Evaluation in SE." (ASE 2025). https://arxiv.org/abs/2505.20854
