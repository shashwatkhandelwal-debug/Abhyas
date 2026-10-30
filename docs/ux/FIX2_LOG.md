# FIX2 log (branch fix/address-and-voice)

Payload baseline (check_first_load.py): first-load 130210 B, all assets 151331 B, headroom 2269 B (real ~1769 B).

## F3 name step: DONE (15:10 IST)
Yes/no and filler words are rejected as names; a leading filler is dropped so "हाँ, मेरा नाम रिया है" stores रिया.
Tests: test_name_extract.py (typed path and service path).

## F1 form of address: DONE
Cause: persona ravi.yaml speech_style said 'दीदी' कहकर बात करता है while the prompt said to address the teacher as सर, so the model combined both. Fixed: removed it from persona data (content and content-seed), prompt now states one rule via address_rule (f: दीदी only, m: सर only, unknown: no address word), and backend/app/llm/address.py fix_address runs on every outgoing child line (model path and template path): collapses combined forms, swaps wrong gender, removes when unknown.
Catalog has no combined keys (checked). Demo accounts: seed sets address_form f (DB only allows f or m); "unknown" is handled at function level.
Tests: test_child_address.py.

## F4 no verbatim repeats: DONE
scene_runner passes this child's previous line and the teacher's words to voice_child_line. Prompt gets the previous line plus "Do not repeat it; react ... keeping the same mistake" (and the teacher's words in the user message). A model line identical to the previous one counts as a failed attempt (retry once, then template). Template path rotates guard-clean variants (_VARIANTS) so consecutive same-state lines differ. Engine state and numbers untouched; guard logic untouched.
Tests: test_child_no_repeat.py.

## F2 hear your own voice note: DONE
chat.js handleSendAudio makes an object URL from the recorded Blob (memory only, nothing uploaded or stored) and puts a play control (reused .bubble-audio) at the top of the outgoing bubble at once; the existing "sending your voice" then "writing out what you said" phase line and the transcript appear under it and the control stays for the page session. URLs are revoked on pagehide and on logout click. Offline outbox and rejected sends keep the control. Server deletes audio after transcription as before.
Payload after: first-load 130791 B, all assets 151912 B, headroom 1688 B measured (real ~1188 B, above the 1000 B floor).
Tests: 3 new node tests in backend/tests/js/chat.test.mjs (harness gained URL stub, firstChild, windowListeners).
