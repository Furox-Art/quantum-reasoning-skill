---
name: quantum-reasoning
description: Explore multiple competing hypotheses in parallel, score and verify them, prune weak branches, and synthesize the strongest surviving evidence before answering.
---

# Quantum Reasoning Skill

Use this skill for problems where early commitment to one reasoning path could cause errors: difficult mathematics, scientific hypotheses, debugging, planning, architecture, diagnosis of technical failures, or ambiguous multi-step analysis.

This is **quantum-inspired classical reasoning**, not quantum computation.

## Protocol

1. **Represent the problem precisely.**
   - State the objective, constraints, known facts, and unknowns.
   - Separate facts from assumptions.

2. **Open diverse branches.**
   - Generate multiple genuinely different candidate hypotheses or solution strategies.
   - Avoid superficial paraphrases of the same path.
   - Increase branch count when uncertainty or consequence is high; reduce it for easy problems.

3. **Score every branch independently.**
   Evaluate each branch on:
   - confidence
   - external verification
   - novelty / independence
   - information gain
   - contradiction penalty

4. **Use tools where they can falsify a branch.**
   Prefer executable checks, numerical tests, formal solvers, source verification, or direct inspection over intuition when available.

5. **Compare branches against each other.**
   - Identify agreements that arise from independent routes.
   - Identify contradictions.
   - Do not treat repeated copies of one assumption as independent evidence.

6. **Allocate compute dynamically.**
   - High uncertainty: widen exploration.
   - Strong evidence: deepen the best branches.
   - Weak, redundant, or contradicted branches: prune early.

7. **Allow recovery from premature pruning when new evidence changes the ranking.**
   Keep a compact record of discarded high-information branches when practical.

8. **Collapse only at the end.**
   Select or synthesize the best-supported result only after comparison and verification.

## Branch score

A practical classical score is:

```text
score =
    confidence * wc
  + verification * wv
  + novelty * wn
  + information_gain * wi
  - contradiction_penalty * wp
```

Normalize scores into probability-like weights. Use the uncertainty of that distribution to decide whether the next step should explore broadly or concentrate compute.

## Output discipline

- Return the final result, not a dump of hidden internal reasoning.
- Surface materially different surviving hypotheses when the problem genuinely remains unresolved.
- State uncertainty explicitly when verification cannot distinguish the leading branches.
- Never claim that classical branch search is actual quantum computation.
