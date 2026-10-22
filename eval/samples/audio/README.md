# Evaluator Sample Audio Files

This directory holds the 5 audio files corresponding to the evaluator sample inputs defined in `eval/samples/samples.yaml`:
- `s1_ask_ravi.wav` — Teacher asking Ravi to explain his subtraction calculation
- `s2_diagnose_one_on_one.wav` — Teacher saying what they think the child's mistake is (1-1 diagnosis step)
- `s3_tell_answer_hinglish.wav` — Teacher telling the direct answer in Hinglish to test relapse / parity
- `s4_explain_back.wav` — Teacher explaining the core move pedagogy back in her own words
- `s5_question_multigrade.wav` — Teacher asking a question about multi-grade classroom management

### Generation & Provenance
Rendered via:
```bash
make samples
# or
python scripts/render_samples.py
```
- **Real Provider Requirement:** Audio files must be synthesized using a real TTS provider (Sarvam AI `bulbul:v3` with `SARVAM_API_KEY` set) or recorded by human voices in `eval/samples/recorded/<id>.wav` / `<id>.ogg` (HUMAN INPUT H15).
- **No Mock Audio in Git:** MockTTS output is silent (RMS = 0) and is strictly disallowed in git. `render_samples.py` will exit with an error if run against MockTTS unless `--allow-mock` is passed explicitly for testing.
- **Dynamic PWA Fallback:** The teacher chat PWA dynamically computes `audio_available` by inspecting whether non-silent WAV files exist on disk. When audio files are absent or silent, demo chips automatically fall back to sending the prompt text.
