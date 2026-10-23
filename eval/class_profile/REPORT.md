# My class: matcher and classifier evaluation

32 sentences labelled by the build team (not by teachers), `eval/class_profile/sentences.yaml`. top-1 = the first id is the expected first id (or both empty); set = same ids in any order; exact = same ids in the same order; none-rejected = off-list sentences that stored nothing.

| System | top-1 | same set | exact order | none-rejected | ids stored for off-list |
|---|---|---|---|---|---|
| keyword matcher (no model) | 31/32 | 30/32 | 30/32 | 5/5 | 0 |
| class_struggle_classifier (Haiku, real) | 31/32 | 31/32 | 31/32 | 5/5 | 0 |
| product path (classifier, then keywords) | 32/32 | 32/32 | 32/32 | 5/5 | 0 |

Real-model spend: about US$0.0041 (cap 1.00); skipped 0.

## Misses: keyword matcher (no model)

- s09: expected ['NUM_ADD_CARRY'], got ['NUM_PLACE_VALUE', 'NUM_ADD_CARRY']
- s13: expected ['NUM_WORD_PROBLEM'], got ['NUM_WORD_PROBLEM', 'LIT_COMPREHENSION', 'NUM_SUB_REGROUP']

## Misses: class_struggle_classifier (Haiku, real)

- s06: expected ['NUM_PLACE_VALUE'], got []

## Misses: product path (classifier, then keywords)

- none
