# Evaluator Sample Audio Files

This directory holds the 5 audio files corresponding to the evaluator sample inputs defined in `eval/samples/samples.yaml`:
- `s1_ask_ravi.wav` — Teacher asking Ravi to explain his subtraction calculation
- `s2_bundles_all.wav` — Teacher modeling concrete bundle representation to the whole class
- `s3_tell_answer_hinglish.wav` — Teacher telling the direct answer in Hinglish to test relapse / parity
- `s4_explain_back.wav` — Teacher explaining the core move pedagogy back in her own words
- `s5_question_multigrade` — Teacher asking a question about multi-grade classroom management

### Generation
Rendered automatically via:
```bash
make samples
# or
python scripts/render_samples.py
```
If real recordings are placed in `eval/samples/recorded/<id>.ogg` or `<id>.wav` (optional HUMAN INPUT H15), `make samples` prefers them over synthetic speech.
