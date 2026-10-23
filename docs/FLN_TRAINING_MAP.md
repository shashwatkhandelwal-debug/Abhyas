# What are teachers trained for? The FLN training map

Built from the committed chunk files (`content/chunks/*.jsonl`, 1,157 chunks) and `content/sources/sources.yaml`.
Everything below is what the chunks say. Chunk ids are `source:pPDF:NNN`; **pp** is the printed page of the
source (the PDF page is in the chunk). Chunks marked **(OCR)** were read from page images by a model
(`content/sources/README.md` has the measured error rate), so quote them with care.

This map is the evidence behind `content/class_struggles.yaml`, the closed list a teacher picks from in "My class".

## 1. What the FLN training covers, per source

| Source (chunks) | What it is | Covers (class 1 to 3) |
|---|---|---|
| **NIPUN Bharat Guidelines, MoE 2021** (294) | The mission document. Defines FLN, the learning outcomes, and the teacher's role | Literacy components (oral language, decoding, fluency, vocabulary, comprehension, writing); numeracy components (pre-number concepts, numbers and operations, shapes, measurement, patterns, data); competency-based learning; assessment; teacher activity checklist; class-wise learning outcomes and the Lakshya (targets) |
| **NISHTHA FLN, NCERT** (281) | The teacher-training package (10 courses) | How children learn; parents and community; Vidya Pravesh/Balvatika; language and early literacy (print awareness, phonological awareness, reading, writing); multilingual classrooms; learning assessment; foundational numeracy pedagogy; leadership; ICT; toy-based pedagogy |
| **NCERT Vidya Pravesh** (67) | 3-month play-based school-preparation module for Grade 1 | Developmental goals (health, communication, learning and environment); weekly plans; phonological awareness; pre-number concepts and number sense; tracking progress |
| **UP Ganit Sandarshika, Class 1** (168, OCR) | Teacher guide, mathematics, Class 1 | Week-by-week lessons (counting, numbers to 20 and 50, add and subtract to 20, measurement, patterns, money, shapes). Each lesson lists a **"सामान्य भूल" (common mistake)** and a NIPUN code. Rule: if fewer than 70% of children answer correctly, mark them and focus on them for the next two periods |
| **UP Bhasha Sandarshika, Class 1** (325, OCR) | Teacher guide, Hindi, Class 1 | NIPUN Hindi list H104 to H109 (rhyme and first sound, reading words made of 2-3 aksharas, reading short sentences, matras, spelling from dictation); weekly plan with akshar recognition, blending, word reading, workbook work |
| `seed_from_moves` (22) | Our own move cards turned into chunks | Not a training source. Used only so the guide can find the 4 moves |

### Competencies the sources name (class 1 to 3)

Numeracy, from the NIPUN Lakshya (`nipun_guidelines_2021:p200:199`, pp 198) and the class-wise outcomes table
(`:p282:283` to `:p284:285`, pp 280-282):
- Class 1: counts objects up to 20, reads and writes numbers up to 99, adds and subtracts numbers up to 9 in daily life; develops own strategies to add two numbers with sum up to 99 (ILM 4.14) and subtract numbers up to 99 (ILM 4.15).
- Class 2: reads and writes numbers up to 999; adds and subtracts up to 99; "appreciates the standard algorithm" for addition and subtraction (ILM 5.14, 5.15); identifies the operation for a problem (ILM 5.20); adds and subtracts small amounts "with or without regrouping" (money, ILM 5.21).
- Class 3: numbers to 9999, zero in the place value system (ILM 6.13), standard algorithm for sums not exceeding 999.

Literacy, from the same Lakshya and the UP Hindi NIPUN list:
- Class 1: sound-symbol correspondence to write words, reads small sentences of 4-5 simple words, "develops familiarity with matras" (H108.2, `up_bhasha_sandarshika_c1:p005:004`, pp 3), writes 2-3 akshar words with more than one matra from dictation (H108.3).
- Class 2: reads 8-10 sentences of an unknown text at about 45 to 60 words per minute with comprehension (`:p200:199`); the 45-60 wpm line is repeated in `nipun_guidelines_2021:p046:039` (pp 44).

### Teaching methods the training asks teachers to use

| Method | Where (chunk, page) |
|---|---|
| Use groups of tens with sticks, pencils and other objects while teaching numbers | NIPUN `p088:082` (pp 86); NISHTHA `p439:316` (pp 427); UP Ganit `p062:100`, `p063:102` (pp 60-61, bundles and loose sticks, OCR) |
| Count by pointing to, touching or moving each object; one-to-one correspondence; number names in order before counting | NIPUN `p087:080` (pp 85); NISHTHA `p436:313` (pp 424) |
| Use manipulatives and toys; hands-on experience | NISHTHA `p447:324` (pp 435) |
| Aim for understanding rather than memorising; let children describe how they solved it | NISHTHA `p130:088` (pp 118); NIPUN `p164:164` (pp 162: express findings first, "gently point out errors") |
| Start from familiar, interesting texts, not the alphabet in sequence; sound and letter attention inside words | NIPUN `p074:068` (pp 72); NISHTHA `p259:179` (pp 247) |
| Build phonological awareness (beginning, middle, end sounds; breaking a word into syllables) | NISHTHA `p036:024` (pp 24); Vidya Pravesh `p032:031` (pp 22) |
| Do not let reading stay akshar by akshar; fluency is needed for comprehension | NIPUN `p075:069` (pp 73) |
| Reading is meaning making: predict, self-correct, re-read | NIPUN `p073:066` (pp 71); NISHTHA `p276:188` (pp 264) |
| Weekly cycle of akshar recognition, blending, word reading (Hindi) | UP Bhasha `p030:051`, `p031:054` (pp 28-29, OCR); `p015:014` (pp 13) |
| Check the class: if under 70% answer correctly, mark those children and give extra attention for the next two periods | UP Ganit `p052:082` (pp 50, OCR) |
| Manage varying abilities with flexible, non-discriminatory grouping | NIPUN `p120:117` (pp 118) |

### Gaps (what the chunks do not give us)

- Only **Class 1** UP guides are ingested. There is no Class 2 or Class 3 UP Ganit or Bhasha text, so nothing in the chunks teaches the *carry* or *borrow* procedure in words. The only support for those is the NIPUN outcomes (ILM 5.14, 5.15) and the "groups of tens" method, which our move cards already build on.
- UP Ganit's Class 1 guide stops at numbers up to 50 and add/subtract up to 20. The "common mistake" lines for two-digit work are one line: "दो अंक की संख्या को जोड़ने में कठिनाई" (`up_ganit_sandarshika_c1:p052:082`).
- No chunk describes matra teaching steps in detail. The UP Bhasha weekly plan names akshar recognition, matra recognition and blending, and the NIPUN list names the matra outcomes, but the step-by-step text lives in the workbook, which we do not have.
- The Hindi UP guides are OCR. Treat any phrase quoted from them as a pointer to a page, not as a verbatim citation, until a human checks the page.
- Some NISHTHA chunks (front matter, course introductions) have no printed page, only a PDF page.

## 2. Class-level struggles mapped to the training

Move cards that exist: `NUM_PLACE_VALUE_BUNDLES`, `NUM_ADD_CARRY_BUNDLES`, `NUM_SUB_REGROUP_BUNDLES`, `LIT_MATRA_BLENDING`.

| # | Struggle (as a class) | Training topic that addresses it | Chunk ids (printed page) | Move card |
|---|---|---|---|---|
| 1 | **Counting and number order**: skip a number, "two" for "three", cannot count backward | Counting needs number names in order, one-to-one correspondence, touching each object | NIPUN `p087:080` (85); NISHTHA `p436:313` (424); UP Ganit `p026:031` (24), `p029:037` (27) | none yet |
| 2 | **Reading and writing numbers**: writes 407 for forty-seven, writes 74 for 47, number names in Hindi | Reading and writing numbers up to 99 and 999 (NIPUN outcomes); number names with bundles | NIPUN `p282:283` (280), `p200:199` (198); UP Ganit `p062:100` (60), `p063:102` (61) | `NUM_PLACE_VALUE_BUNDLES` (writing and reversal mistakes) |
| 3 | **Place value (tens and ones)**: counts a bundle as 1, mixes up tens and ones | Groups of tens with sticks and bundles; zero in place value | NIPUN `p088:082` (86), `p282:283` (280); NISHTHA `p439:316` (427); UP Ganit `p063:102` (61) | `NUM_PLACE_VALUE_BUNDLES` |
| 4 | **Comparing numbers**: bigger-looking object is "more", wrong order of two numbers | Comparing and ordering numbers; vocabulary more/less | NIPUN `p283:284` (281); UP Ganit `p030:039` (28), `p040:058` (38) | none yet |
| 5 | **Addition with carry**: forgets the carried 1, writes 13 whole | Strategies then the standard algorithm for addition (ILM 4.14, 5.14); groups of tens | NIPUN `p283:284` (281); NISHTHA `p439:316` (427); UP Ganit `p052:082` (50) | `NUM_ADD_CARRY_BUNDLES` |
| 6 | **Subtraction with regrouping**: takes the smaller digit from the larger, forgets to reduce the tens | Strategies then the standard algorithm for subtraction (ILM 4.15, 5.15); relation of add and subtract | NIPUN `p283:284` (281), `p284:285` (282); UP Ganit `p044:067` (42) | `NUM_SUB_REGROUP_BUNDLES` |
| 7 | **Word problems**: cannot tell add from subtract in a story | Identify the operation in a familiar situation (ILM 5.20); language of the question | NIPUN `p284:285` (282); UP Ganit `p048:074` (46), `p051:080` (49) | none yet |
| 8 | **Small add and subtract facts (to 20)**: slow, counts all, mixes the two | Count-on; add and subtract with concrete objects | UP Ganit `p043:065` (41), `p047:072` (45); NIPUN `p283:284` (281) | none yet |
| 9 | **Matras missing**: leaves out the matra (मेला read as मल) | NIPUN H108.2, H108.3; weekly akshar, matra and blending plan | NIPUN `p200:199` (198); UP Bhasha `p005:004` (3), `p015:014` (13) | `LIT_MATRA_BLENDING` (MATRA_DROP) |
| 10 | **Reads akshar by akshar**, no blending, slow | Reading fluency: laboured akshar-by-akshar reading hampers meaning; blending practice | NIPUN `p075:069` (73), `p046:039` (44); UP Bhasha `p030:051` (28) | `LIT_MATRA_BLENDING` (AKSHAR_BY_AKSHAR) |
| 11 | **Guesses words from the first akshar** | Decoding from the relation of symbols and sounds, self-correction | NIPUN `p074:068` (72), `p073:066` (71); NISHTHA `p276:188` (264) | `LIT_MATRA_BLENDING` (FIRST_AKSHAR_GUESS) |
| 12 | **Letters and sounds**: cannot name aksharas or give their sounds | Phonological awareness; akshar knowledge and decoding; letter-sound in context | NIPUN `p074:068` (72); NISHTHA `p036:024` (24), `p259:179` (247); Vidya Pravesh `p032:031` (22); UP Bhasha `p030:051` (28) | none yet |
| 13 | **Comprehension**: reads aloud but cannot say what it means | Reading comprehension; reading as meaning making | NIPUN `p073:066` (71); NISHTHA `p292:201` (280), `p276:188` (264) | none yet |
| 14 | **Writing and spelling**: cannot write a word from dictation, wrong matra when writing | Writing development; spelling from sound-symbol correspondence | NIPUN `p200:199` (198); UP Bhasha `p005:004` (3); NISHTHA `p292:201` (280) | none yet |

Literacy struggles 9 to 11 are all covered by one move card because the move's own causes
(`MATRA_DROP`, `AKSHAR_BY_AKSHAR`, `FIRST_AKSHAR_GUESS`) are exactly these three.

## 3. Coverage summary

- **14 struggles**, mapped to training topics with chunk citations. Every one has at least one NIPUN, NISHTHA or UP chunk.
- **Has a practice scene (6 of 14):** place value (3), addition with carry (5), subtraction with regrouping (6), and the three matra/blending causes (9, 10, 11). Struggle 2 (reading and writing numbers) is only partly covered, through the writing and reversal mistakes in the place-value move.
- **Handbook tip only, "no practice case yet" (7 of 14):** counting (1), comparing numbers (4), word problems (7), small facts (8), letters and sounds (12), comprehension (13), writing and spelling (14).
- Practice scenes exist for 4 moves, so numeracy is covered for the two-digit work of Class 2 and literacy only for matra blending. Counting, letters and comprehension are the biggest missing practice cases, and the Class 1 UP guides give the strongest text for them.
