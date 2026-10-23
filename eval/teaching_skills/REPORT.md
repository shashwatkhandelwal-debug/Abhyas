# Teaching skills: classifier evaluation

16 sentences labelled by the build team (not by teachers), `eval/teaching_skills/sentences.yaml`. top-1 = the first id is the expected first id (or both empty); set = same ids in any order; exact = same ids in the same order; none-rejected = vague or off-topic sentences that stored nothing (the chips come back).

| System | top-1 | same set | exact order | none-rejected | ids outside the list |
|---|---|---|---|---|---|
| teaching_skill_classifier (Haiku, real) | 16/16 | 16/16 | 16/16 | 3/3 | 0 |

Real-model spend: about US$0.0010 (cap 0.50); skipped 0. A call that fails its guard twice returns nothing (counted as no id) and the numbered list is shown.

## Misses

- none
