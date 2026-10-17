# Recorded Human Voice Samples

This directory holds authentic voice recordings of government primary FLN teachers speaking the 5 evaluator sample inputs defined in [`eval/samples/samples.yaml`](../samples.yaml).

> [!IMPORTANT]
> **Strict Anonymity Rule:** In accordance with the Digital Personal Data Protection Act 2023 (DPDP) and project ethics rules, **never use personal names, teacher names, phone numbers, or school names** in filenames or audio metadata. Only the canonical sample IDs (`<id>`) are permitted.

---

## 1. File Naming Conventions

Audio files must match the canonical sample IDs from `eval/samples/samples.yaml` with standard audio extensions:

- `s1_ask_ravi.(wav|ogg|m4a)` — Teacher asking Ravi how he subtracted 27 from 43
- `s2_bundles_all.(wav|ogg|m4a)` — Teacher modeling bundle representation to the whole class
- `s3_tell_answer_hinglish.(wav|ogg|m4a)` — Teacher telling direct answer in Hinglish to test relapse
- `s4_explain_back.(wav|ogg|m4a)` — Teacher explaining back the core move pedagogy
- `s5_question_multigrade.(wav|ogg|m4a)` — Teacher asking about multi-grade subtraction management

Acceptable file formats:
- `.wav` (PCM 16kHz or 48kHz mono, uncompressed)
- `.ogg` (Ogg Opus mono, standard WhatsApp voice note format)
- `.m4a` (AAC mono, standard smartphone voice recorder format)

---

## 2. Recording Protocol

1. **Speaker Profile**: Government primary teacher (Classes 1–3, FLN), fluent Hindi speaker.
2. **Environment**: Natural indoor environment representative of school conditions (staffroom or quiet classroom; normal ambient acoustic background, not soundproof studio).
3. **Delivery Cadence**: Natural, unhurried conversational cadence in Hindi as a teacher addressing students or an AI practice partner.
4. **Pacing and Volume**: Conversational classroom teaching volume (approx. 60–65 dB SPL at microphone distance 15–20 cm).
5. **No Synthetic Audio**: Never place text-to-speech (TTS) audio files in this directory. Evaluators inspect provenance to verify authentic human speech error rates.

---

## 3. Consent and Data Protection Requirements

1. **Informed Consent**: Every participating teacher must review and sign the Hindi informed consent form (`eval/user_testing/consent_form_hi.md`) prior to recording.
2. **Purpose Limitation**: Audio recordings are collected strictly for calculating Word Error Rate (WER) and Character Error Rate (CER) on the configured STT engine (`make eval-stt`).
3. **Retention and Storage**:
   - Audio files in this directory are restricted to research and benchmarking and are gitignored if containing unreleased identifiable voice data.
   - Only calculated WER/CER aggregate metrics are published in [`eval/stt/REPORT.md`](../../stt/REPORT.md).
4. **Right to Withdraw**: Any participant may request deletion of their recordings at any time; upon request, the corresponding audio file will be purged immediately.
