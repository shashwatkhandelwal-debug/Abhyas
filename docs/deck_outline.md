# Deck outline (8–10 slides)

Facts only; replace every TODO(human) with a real measured number or omit the claim. Diagrams and screenshots go in `docs/deck_assets/`.

1. **Title.** Abhyas, Team Asymptotes, Challenge 3 (Teacher Support and Training).
2. **AI in layers.** The layered diagram from the README. Table of the seven runtime Claude roles: where called, what it does, model (fast: intent_router, act_tagger, child_voice, question_classifier; smart: coach, fidelity_checker, guide_answerer), which guard.
3. **Core innovation.** Deterministic misconception engine plus LLM voice. Ravi example (43 − 27 → 24). TODO(human): blind realism result, only if the survey was run.
4. **Guardrails.** Schema validation, number/answer guard, quote-exists guard, sources ⊆ retrieved, confidence → human review, deterministic fallbacks. Use three blocked examples and the rates from `eval/guards/REPORT.md`; label corpus cases as test cases and live rates as live.
5. **Evaluation.** Kappa vs coaches (n, value, CI), latency p50/p95, realism mean. Report n and limitations honestly. TODO(human): numbers from the final runs.
6. **Real scenarios.** Low-connectivity table, data per week, low-cost Android, WhatsApp-first, Hindi/Hinglish voice, 15 minutes a week; what needs network and what degrades.
7. **User testing (1).** Who, how many, protocol (`eval/user_testing/`). TODO(human): real counts.
8. **User testing (2).** Top findings, what changed, two real quotes with consent.
9. **Roadmap.** IVR for feature phones; Bhashini and more languages; DIKSHA/Prerna and the Sankul cycle; DIET/SCERT dashboards; opt-in class-audio coaching; child-outcome link; content pipeline with SCERT coaches; cost per teacher per year (TODO(human): from measured spend).
10. **Privacy, safety and the ask.** DPDP alignment, no audio stored, consent gates, n ≥ 10, children never scored.

Speaker notes: one paragraph per slide drawn from the README; do not add claims the repo cannot back.
