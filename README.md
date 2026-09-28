# Quantum Reasoning Skill  
  
[![PyPI](https://img.shields.io/pypi/v/quantum-reasoning-skill)](https://pypi.org/project/quantum-reasoning-skill/)  
[![npm](https://img.shields.io/npm/v/quantum-reasoning-skill)](https://www.npmjs.com/package/quantum-reasoning-skill)  
![License](https://img.shields.io/badge/license-MIT-blue)  
  
A **model-agnostic reasoning skill** that keeps multiple genuinely different possibilities alive, verifies and compares them, suppresses weak paths, revives useful alternatives when evidence changes, and selects the best-supported result only at the end.  
  
## When to use  
  
Use this skill when a problem is difficult, ambiguous, high-stakes, multi-step, or vulnerable to early commitment: mathematics, scientific reasoning, debugging, planning, architecture, model selection, hypothesis testing, and technical diagnosis.  
  
Do not add branching overhead to trivial questions.  
  
## Core protocol  
  
### 1. Frame the state  
  
Identify the objective, constraints, verified facts, assumptions, unknowns, and available tools. Keep facts separate from hypotheses.  
  
### 2. Open a diverse possibility set  
  
Create several materially different candidate paths. Diversity is mandatory: do not count paraphrases, cosmetic variants, or branches that depend on the same hidden assumption as independent possibilities.  
  
Prefer orthogonal strategy classes when applicable, such as:  
  
- direct derivation  
- counterexample / falsification  
- decomposition  
- alternative model or mechanism  
- numerical or executable test  
- independent reconstruction  
- adversarial critique 
