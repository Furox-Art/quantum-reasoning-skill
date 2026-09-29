# Quantum Reasoning Skill  
  
[![PyPI](https://img.shields.io/pypi/v/quantum-reasoning-skill)](https://pypi.org/project/quantum-reasoning-skill/)  
[![npm](https://img.shields.io/npm/v/quantum-reasoning-skill)](https://www.npmjs.com/package/quantum-reasoning-skill)  
![License](https://img.shields.io/badge/license-MIT-blue)  
  
I built this because I noticed that most AI reasoning goes like this:  
  
1. Here's a plausible answer  
2. Let me justify it  
3. Done  
  
That's backwards. Real thinking explores multiple paths, tests them against evidence, and only commits when the alternatives have been genuinely eliminated.  
  
This skill forces that process. It keeps multiple hypotheses alive, assigns them probabilities based on actual evidence (not just "sounds good"), and collapses to a conclusion only when one path is clearly better supported than the rest.  
  
## The protocol  
  
1. **Frame the problem** - what do we actually know vs. assume?  
2. **Open branches** - generate genuinely different approaches, not paraphrases  
3. **Evaluate independently** - each branch gets judged on evidence, not eloquence  
4. **Cross-check** - branches that reach the same conclusion independently get boosted  
5. **Prune and revive** - kill contradicted paths, but keep dormant ones that might come back  
6. **Collapse** - only when one answer is clearly better than the rest  
  
## Why "quantum"?  
  
It's a metaphor, not a claim about actual quantum computing. The idea is to keep possibilities in superposition until measurement (evidence) forces a collapse. Most AI systems measure too early.  
  
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
