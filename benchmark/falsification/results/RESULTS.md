# Falsification benchmark results

## Aggregate summary

| metric | single-hypothesis | multi-hypothesis |
|---|---:|---:|
| overall accuracy | 0.222 | 1.000 |
| falsification-scenario accuracy | 0.000 | 1.000 |
| decision-switch success rate | 0.000 | 1.000 |
| mean switch delay (evidence steps) | n/a | 0.000 |
| revival success rate | 0.000 | 1.000 |
| control-scenario accuracy | 1.000 | 1.000 |
| Brier score (lower is better) | 0.033 | 0.033 |
| mean tokens per scenario | 115.6 | 242.2 |
| mean latency per decision (ms) | 0.013 | 0.052 |

## Per-scenario results

| scenario | type | policy | final answer | correct | switch | revival | tokens |
|---|---|---|---|---|---|---|---:|
| falsification-001 | falsification | single | H_A | no | no | n/a | 130 |
| falsification-001 | falsification | multi | H_B | yes | yes (+0) | n/a | 238 |
| falsification-002 | falsification | single | H_A | no | no | n/a | 104 |
| falsification-002 | falsification | multi | H_B | yes | yes (+0) | n/a | 188 |
| falsification-003 | falsification | single | H_A | no | no | n/a | 104 |
| falsification-003 | falsification | multi | H_B | yes | yes (+0) | n/a | 188 |
| falsification-004 | falsification | single | H_A | no | no | n/a | 130 |
| falsification-004 | falsification | multi | H_B | yes | yes (+0) | n/a | 268 |
| revival-001 | revival | single | H_A | no | n/a | no | 130 |
| revival-001 | revival | multi | H_B | yes | n/a | yes | 280 |
| revival-002 | revival | single | H_A | no | n/a | no | 130 |
| revival-002 | revival | multi | H_C | yes | n/a | yes | 310 |
| revival-003 | revival | single | H_A | no | n/a | no | 130 |
| revival-003 | revival | multi | H_C | yes | n/a | yes | 292 |
| control-001 | control | single | H_A | yes | n/a | n/a | 104 |
| control-001 | control | multi | H_A | yes | n/a | n/a | 230 |
| control-002 | control | single | H_A | yes | n/a | n/a | 78 |
| control-002 | control | multi | H_A | yes | n/a | n/a | 186 |
