# ONLINE research evaluation

The hypothesis is that evidence-gap-driven typed graph expansion can preserve retrieval and
citation quality while visiting fewer nodes/edges than fixed expansion. The required
baselines are BM25, Dense, flat RRF hybrid and fixed/disabled graph retrieval. Ablations
cover hub penalty and graph enablement. Metrics are recall@k, citation validity, wrong-version
count, latency, nodes visited and retrieval rounds.

The first run uses the AI-prechecked but DRAFT 17-query set, so it is diagnostic only:

| Method | Draft recall@10 | Average latency |
|---|---:|---:|
| BM25 | 0.6979 | 58.23 ms |
| Dense | 0.5833 | 2317.31 ms |
| Hybrid RRF | 0.6979 | 140.35 ms |

Dense latency includes model cold start in this sequential runner. No method is promoted and
no threshold is changed from these results. `artifacts/online_evaluation/retrieval_benchmark.json`
records build `0c4d82edb5e23df65490b5b2eb9cb5623c2d5f1a8baf75693acf6329af9a92cc`
and status `PROVISIONAL_DRAFT_GOLD`.

Official research evaluation requires a real reviewer to approve questions, qrels and
thresholds, a rebuilt OFFLINE build with reviewed temporal intervals, and rerunning every
baseline/ablation against the same fingerprints. Negative findings must be retained.
