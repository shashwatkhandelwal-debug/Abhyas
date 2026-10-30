# FIX2 log (branch fix/address-and-voice)

Payload baseline (check_first_load.py): first-load 130210 B, all assets 151331 B, headroom 2269 B (real ~1769 B).

## F3 name step: DONE (15:10 IST)
Yes/no and filler words are rejected as names; a leading filler is dropped so "हाँ, मेरा नाम रिया है" stores रिया.
Tests: test_name_extract.py (typed path and service path).
