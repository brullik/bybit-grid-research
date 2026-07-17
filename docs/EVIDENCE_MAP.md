# Evidence Map

## Control plane

| Evidence | Disposition |
|---|---|
| PR #69 immutable PM control plane | merged |
| PR #70 protected-path attack probe | closed unmerged |
| PR #71 strict persisted-models task definition | governed history |
| PR #86 autonomous aggregate-status lifecycle | merged |
| PR #104 atomic-install v2 task/control-plane revision | merged |

Required PR checks are protected-paths, acceptance (3.12), acceptance (3.14) and aggregate pm-acceptance. RED probe success means exact expected failures followed by closure without merge.

## Governed canonical-store lifecycles

| Boundary | Task / RED / implementation / close |
|---|---|
| Strict persisted models/parsers | #71 / #74 closed unmerged / #75 / #76 |
| Strict chunk path and I/O | #77 / #78 closed unmerged / #79 / #80 |
| Context-free Decimal identity | #81 / #82 closed unmerged / #83 / #84 |
| Strict canonical graph audit | #87 / #88 closed unmerged / #89 / #90 |
| Portable owner seed pack | #91 / #92 closed unmerged / #93 / #94 |
| Atomic owner seed install, final v2 chain | #104 + erratum #105 / #106 closed unmerged / #107 / #108 |

The earlier atomic-install chain #95–#103 contained invalid or cancelled evidence and is not the final implementation chain. It remains history, not a production GREEN substitute.

## Recent offline lifecycles

| Boundary | Task / RED / implementation / close |
|---|---|
| 06.4C historical plan | #110 / #111 closed unmerged / #112 / #113 |
| 06.4D response acceptance | #115 / #116 closed unmerged / #117 / #118 |
| 06.4E transcript | #120 / #121 closed unmerged / #122 / #123 |
| 06.4F evidence layout | #125 / #126 closed unmerged / #127 / #128 |

## P0 private transport

- Task #135 merged.
- Invalid predecessor #137 and probe #138 were not accepted as final evidence.
- Cancellation #139 merged.
- Frozen erratum #140 merged.
- Fresh mandatory RED #141 closed Draft and unmerged.
- Implementation #142 merged after Ready run 29540177525, Python 3.12/3.14 and 513 ordinary tests.
- Task-close #143 merged after Ready run 29553808388 and canonical NO_ACTIVE_IMPLEMENTATION.
- Issue #130 closed completed.

## Assurance caveat

PR #1–66 predate the immutable control plane. Sampled #1, #2, #20, #40, #59 and #66 lack retained status/review evidence. Current green tests are not retroactive proof. Issue #134 must classify and revalidate current-main behavior without executing historical branch code.

## Repository-history caveat

A fresh 2026-07-17 ref inventory recorded in issue #133 found 136 branch refs, superseding the issue body's earlier 127-branch audit snapshot. Full reachable-history secret scanning is not yet proven. No branch cleanup or real credential use is authorized before a sanitized owner-local scan and retention proof.

GitHub links use https://github.com/brullik/bybit-grid-research/pull/NUMBER or /issues/NUMBER. Merge status must be verified from GitHub; this static map is an evidence index, not current authority.
