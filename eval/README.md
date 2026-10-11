# Evaluation Suite (`eval/`)

Evaluation harnesses to measure and calibrate performance against the targets defined in Section 15 of `ARCHITECTURE.md`.

## Target Metrics
| Metric | Target | Tool / Script |
|---|---|---|
| AI Coach vs Expert Coaches | $\kappa \ge 0.70$ | `calibration/evaluate_kappa.py` |
| Explain-it-Back Scoring vs Coaches | $\kappa \ge 0.70$ | `calibration/evaluate_kappa.py` |
| Realism of AI Children | $\ge 4$ of $5$ | `realism/survey_analysis.py` |
| Weekly Active Teachers | $\ge 50\%$ over 6 weeks | Engagement logs in database |
| End-to-End Latency | $< 20\text{s}$ for 95% of turns | `latency/benchmark_latency.py` |
