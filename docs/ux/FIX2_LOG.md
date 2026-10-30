# FIX2 log (branch fix/address-and-voice)

Payload baseline (check_first_load.py): first-load 130210 B, all assets 151331 B, headroom 2269 B (real ~1769 B).

## F3 name step: DONE (15:10 IST)
Yes/no and filler words are rejected as names; a leading filler is dropped so "हाँ, मेरा नाम रिया है" stores रिया.
Tests: test_name_extract.py (typed path and service path).

## F1 form of address: DONE
Cause: persona ravi.yaml speech_style said 'दीदी' कहकर बात करता है while the prompt said to address the teacher as सर, so the model combined both. Fixed: removed it from persona data (content and content-seed), prompt now states one rule via address_rule (f: दीदी only, m: सर only, unknown: no address word), and backend/app/llm/address.py fix_address runs on every outgoing child line (model path and template path): collapses combined forms, swaps wrong gender, removes when unknown.
Catalog has no combined keys (checked). Demo accounts: seed sets address_form f (DB only allows f or m); "unknown" is handled at function level.
Tests: test_child_address.py.
