# Quantum Reasoning Skill  
  
[![PyPI](https://img.shields.io/pypi/v/quantum-reasoning-skill)](https://pypi.org/project/quantum-reasoning-skill/)  
[![npm](https://img.shields.io/npm/v/quantum-reasoning-skill)](https://www.npmjs.com/package/quantum-reasoning-skill)  
![PyPI Downloads](https://img.shields.io/pypi/dm/quantum-reasoning-skill)  
![License](https://img.shields.io/badge/license-MIT-blue)  
  
I built this because I noticed that most AI reasoning goes like this:  
  
1. Here's a plausible answer  
2. Let me justify it  
3. Done  
  
That's backwards. Real thinking explores multiple paths, tests them against evidence, and only commits when the alternatives have been genuinely eliminated.  
  
This skill forces that process. It keeps multiple hypotheses alive, assigns them probabilities based on actual evidence (not just "sounds good"), and collapses to a conclusion only when one path is clearly better supported than the rest.  
  
## Quick Start  
  
```bash
pip install quantum-reasoning-skill
```

```python
from quantum_reasoning_skill import ReasoningSession

session = ReasoningSession(problem="Should we migrate our monolith to microservices?")
session.open_branch("strangler-fig incremental")
session.open_branch("big-bang rewrite")
session.open_branch("modular monolith refactor")

session.evaluate(evidence="team has zero k8s experience", branch="big-bang rewrite", impact=-0.4)
session.evaluate(evidence="current deploys take 45min", branch="modular monolith", impact=+0.2)

verdict = session.collapse()
print(verdict.winner, verdict.confidence, verdict.rejected)
```

Also available as an [Agent Skill](SKILL.md) for Claude and MCP-compatible hosts, and on npm: `npm i quantum-reasoning-skill`.

## How it compares

| Approach | What it does | Where it falls short |
|---|---|---|
| Chain-of-Thought | One linear reasoning path | Early anchoring; no alternatives kept alive |
| Tree-of-Thought | Branches + scoring | Static scoring; no evidence weighting or revival |
| Self-consistency | Samples the same prompt N times | Paraphrase diversity, not genuine hypothesis diversity |
| **This skill** | Branches with evidence-weighted probabilities, cross-checking, pruning with revival, and explicit collapse criteria | — |

## The protocol  
  
1. **Frame the problem** - what do we actually know vs. assume?  
2. **Open branches** - generate genuinely different approaches, not paraphrases  
3. **Evaluate independently** - each branch gets judged on evidence, not eloquence  
4. **Cross-check** - branches that reach the same conclusion independently get boosted  
5. **Prune and revive** - kill contradicted paths, but keep dormant ones that might come back  
6. **Collapse** - only when one answer is clearly better than the rest  
  
## Why "quantum"?  
  
It's a metaphor, not a claim about actual quantum computing. The idea is to keep possibilities in superposition until measurement (evidence) forces a collapse. Most AI systems measure too early.  
  
## Common use cases

- **Multi-branch reasoning** for difficult questions where one early answer can anchor the rest of the analysis.
- **AI agent planning and decision support** with explicit competing hypotheses.
- Evidence-based **problem solving, search, pruning, and branch selection**.
- Scientific or technical analysis where independent approaches should be compared before a conclusion is chosen.
- Benchmarking reasoning systems that need an inspectable explore-score-prune-merge protocol.

## Documentation

- [SKILL.md](SKILL.md) — agent skill contract and protocol
- [Usage examples](examples/usage.md)
- [Host integration](examples/host-integration.md)
- [Branch controller reference](reference/branch_controller.py)
- [Measurement methodology](docs/MEASUREMENT.md)
- [Compatibility notes](docs/COMPATIBILITY.md)
- [Benchmark documentation](benchmark/README.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Citation metadata](CITATION.cff)

## License  
  
MIT. 
