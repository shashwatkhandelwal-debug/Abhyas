# Pitch notes (Team Asymptotes, Challenge 3: Teacher Support and Training)

Honest by design: every claim below is either an external source named with its figure, or something this repository
shows. Nothing here says Abhyas improves learning. What a pilot would measure is in the Q&A.

## 1. Problem to feature

Evidence is quoted exactly as supplied, with its source. Only these sources are used.

| Problem (evidence) | What Abhyas does about it | Where to see it |
|---|---|---|
| **Mixed levels, multigrade rooms.** ASER school observations: two-thirds of Class 1 and 2 classrooms were multigrade (as cited in countercurrents.org, Aug 2026). UDISE+ 2024-25: 1,04,125 single-teacher schools (7.1%) serving about 33.8 lakh students. J-PAL: Teaching at the Right Level raised test scores by 0.07 to 0.70 standard deviations across six randomized evaluations in seven Indian states. | **Level sorter.** Tap rough counts per level; get 2-3 groups, who to sit with first, and one 10-minute activity per group taken from stored handbook chunks, each cited. A multigrade line appears only for reading, where a stored UP handbook passage supports it. | Chip "Group my class by level" |
| **Training does not reach practice; no support after training.** Parliamentary Standing Committee (368th report): about 10 lakh teaching posts vacant in Samagra Shiksha schools, about 7.5 lakh at elementary and primary level. TLPS 2025 (Language and Learning Foundation, Tata Trusts): 1,050 early-grade classrooms in nine states; classroom talk largely choral and writing largely copying. | **Class check-in + rehearsal.** After class, a few taps (topic, how it went, which difficulty) give one cited handbook tip and, where a practice case exists, a rehearsal with a simulated child whose answers come from a rule engine, never from a language model. | Chip "After class: how did it go?"; the Ravi scene |
| **Digital tools lose most teachers.** CSBC/Ashoka field trial with about 1,900 grade 3 teachers in Sitapur and Hardoi (UP): neither the WhatsApp chatbot nor micro-videos improved adoption, knowledge or valuation across the sample; only 15-20% stayed consistently active; reasons included time, multigrade classes, admin work, too many resources, patchy connectivity, and third-party material feeling less official. | Two-minute flows; taps instead of typing; every tip carries its official source and a national or state label; works on low bandwidth (under 150 KB first load) and queues messages offline; **cluster meeting pack** so use is anchored in the meeting a mentor already runs. | Citation chips; low-network mode; ARP and trainer pages |
| **Weak classroom talk.** TLPS 2025: classroom talk largely choral. Tamil Nadu state report: only 18% of teachers consistently gave children wait time. | **Talk-move feedback.** At the end of a practice scene: one strength and one next step from what the teacher did (named child vs whole class, asked how or why vs only checked, told the answer), quoting her own words. It does not measure wait time. | Coach feedback after a scene |
| **Time pressure.** NIEPA time-use study: teachers spend about 19% of time on teaching and teaching-related activities (as reported by accountabilityindia.in). Shiksha Copilot (Cornell / Microsoft Research India), grades 5-10 in Karnataka: teachers estimated about two hours saved per week (self-reported); no learning outcomes published. | Taps, not typing; flows of about two minutes; voice in Hindi. We make no time-saving claim: nothing here has been measured with teachers. | Whole product |
| **Mentors buried in admin.** The NIEPA figure above is about teachers; we have no figure for mentors, so this row is a design judgement, not evidence. | **Cluster meeting pack.** From check-in counts of consenting teachers (groups under 10 hidden): the top 2 reported difficulties, one move to practise together, and a printable one-page agenda. | ARP and trainer pages |

Other evidence we may cite: ASER 2024 (Pratham): Standard 3 children who could at least subtract rose from 20.9% in 2018 to 27.6% in 2024. PARAKH Rashtriya Sarvekshan 2024 (NCERT): Class 3 national average 64% language, 60% maths.

Source links: ASER 2024 https://pratham.org.uk/unveiling-prathams-annual-status-of-education-report-2024-transforming-insights-into-action-for-indias-education-future/ ; PARAKH https://news.careers360.com/parakh-rashtriya-sarvekshan-result-2024-state-govt-schools-sc-st-far-behind-class-3-6-9-maths-science-language-evs-exam-survey ; UDISE+ https://educationforallinindia.com/school-education-in-india-where-do-we-stand-analysis-of-udiseplus-2024-25-data/ ; multigrade https://countercurrents.org/2026/08/indias-vanishing-primary-school/ ; NIEPA https://accountabilityindia.in/blog/relooking-non-teaching-roles-of-government-school-teachers/ ; vacancies https://news.careers360.com/10-lakh-school-teacher-posts-vacant-kvs-nvs-ncte-6-year-hiring-parliamentary-committee-nep-policy-not-practical-temporary-itep ; CSBC/Ashoka https://idronline.org/article/education/why-digital-nudges-alone-wont-transform-classrooms/ ; J-PAL https://www.povertyactionlab.org/policy-insight/tailoring-instruction-students-learning-levels-increase-learning ; TLPS https://idronline.org/kn-in/article/education/rethinking-the-foundations-of-early-learning/ and https://www.dtnext.in/news/tamilnadu/94-percent-of-primary-class-teachers-know-foundational-literacy-numeracy-goals-tlps-report ; Shiksha Copilot https://news.cornell.edu/node/333759

## 2. Built versus roadmap

| | Status | Notes |
|---|---|---|
| Teacher form of address follows the onboarding choice (she / he) | **Built** | Tested for both forms |
| After-class check-in (closed lists, one cited tip, practice launch) | **Built** | No child data, no free text, works inside a paused scene |
| Child understanding strip in practice scenes | **Built** | Labels from existing engine state; a child who was only told the answer shows as "stuck", not "stuck again" (that would need an engine change) |
| Level sorter (reading and maths) | **Built** | Level names are ours; activities only from stored UP handbook chunks |
| Talk-move feedback | **Built** | From tagged acts, no extra model call; no wait-time measurement |
| National / state labels on citations; national tie-break in retrieval | **Built** | UP is the only state pack ingested |
| Cluster meeting pack with printable agenda | **Built** | Demo cluster 1 shows the privacy rule (7 consenting teachers, hidden); the trainer view shows the full pack |
| Per-channel button limits (web 5; WhatsApp 3 reply buttons, a list beyond that) | **Built** | Tested; not exercised on live WhatsApp |
| Next-day follow-up after a check-in (worked / still stuck / could not try, with a reason) | **Built** | Closed lists, a different cited source on "still stuck", stored once per follow-up; web only (WhatsApp has no "chat opened" event) |
| ARP class-visit checklist (talk moves seen, practice seen, one next step) | **Built** | No free text, no child data; consenting teachers only |
| "Reported vs observed" trainer card | **Built** | Counts only, hidden below 10 teachers; self-reported and observed, not outcomes |
| Adaptive next practice with a one-line reason | **Built** | Deterministic reorder among her own moves; demo3 needs a whole week to reach it |
| Opt-in daily "आज का सुझाव" card in the web chat | **Built** | Asked once a week at most, one cited step a day, never inside a scene she has started; nothing is sent over WhatsApp |
| Scene: comparing two-digit numbers (child compares the ones first) | **Built** | One deterministic rule; text-only board; key points from stored chunks, the "bundles first" step is our own design |
| Scene: letter name versus letter sound ("ब से बतख") | **Built** | The stored chunks name no confusable letter pair, so the scene uses the name-versus-sound confusion; group only |
| Trainer "Where training is not landing" | **Built** | Latest simulated rehearsal per consenting teacher and move, counts only, cells under 10 withheld; CSV rows function exists, wired on merge |
| Experience-aware start ("straight to practice" for 6+ years) | **Built** | New teachers keep model practice first; the learn step is recorded as skipped, counts only |
| Neutral ARP wording, and the ARP's visit note shown to the teacher | **Built** | See section 2c; a school-setting question is not built |
| Audio on the model practice | Roadmap | No cached audio exists; a human prewarm run is needed (`docs/ux/TRACKB_LOG.md`) |
| Regional languages via Bhashini | Roadmap | A Bhashini client file exists in the repo; the product is Hindi and English only |
| Home-language bridging scenes | Roadmap | |
| IVR for teachers without a smartphone | Roadmap | |
| A real WhatsApp pilot | Roadmap | Needs Meta credentials and teachers |
| Classroom-outcome measurement | Roadmap | No real teacher has used the system |

## 2b. Measurement plan for a pilot

What a pilot would measure, from data the product already stores as closed lists (no free text, no child data):

- **Check-ins per week per teacher**, and the share of teachers who do one in weeks 1, 3 and 6 (the field trial's problem was drop-off, so week-3 return is the first number).
- **Follow-up outcomes**: of the follow-ups offered, how many were answered, and the split between "worked", "still stuck" and "could not try" with the reasons (time, several grades, children absent, other).
- **Observed talk moves**: the ARP's tick-list per visit (named a child, asked why or how, did not just tell the answer, gave time to think), compared with what the same teachers reported.
- **Follow-through**: whether the practice from the last check-in was seen on the visit.

What it would NOT claim:

- No learning-outcome claim. Nothing here measures what children learned.
- No classroom-impact claim. Reported and observed counts show what teachers say and what an ARP saw on a visit; the two can disagree, and the card puts them side by side on purpose.
- No comparison with other tools, no causal claim, no per-teacher ranking. Aggregates are shown only for 10 or more consenting teachers.
- The demo numbers are made-up demo data and are labelled so; they say nothing about real teachers.

## 2c. The monitoring constraint

Teachers are wary of tools that watch them in order to assess them. A tool that feels like inspection gets avoided, so
the design treats support, not monitoring, as a requirement. What is built, and what is not:

| Design choice | Status | Where to see it |
|---|---|---|
| Sharing is the teacher's own choice. Scores go to an ARP only for teachers who agreed; everyone else is a count ("other N teachers, scores not shared"). | **Built** | ARP page; test that a teacher who has not agreed shows no name or score on the ARP or trainer pages |
| ARP wording is about help, not deficit: "Practise together" in a neutral colour instead of a red "Needs help", and one line above every per-teacher list: these teachers share their scores by choice, this is for support, not evaluation. | **Built** (flag SUPPORT_FRAMING_ENABLED, on in demo mode) | ARP page |
| The teacher sees what her ARP noted about her class, in her own chat: "Your ARP noticed: ... One thing to try: ...", with an OK button. Closed lists only, no score, no level, and it feeds nothing. | **Built** (flag OBSERVATION_TO_TEACHER_ENABLED, on in demo mode) | Save a visit on the ARP page for demo2, then open demo2's chat |
| Trainers and DIET see counts, never a teacher, and nothing below 10 teachers. The training-gap table says in its caption that it comes from simulated rehearsals, not classroom observation. | **Built** | Trainer page: "Where training is not landing" |
| The daily tip is opt-in, asked once a week at most, and one tap turns it off. | **Built** (flag FOCUS_CARD_ENABLED) | Chat, after a check-in or a finished practice |
| School-setting question (village, town, several classes in one room) to tune the level sorter and handbook order, never shown to an ARP as an individual attribute. | **Not built** | Needs a new teacher column and an onboarding step; left for after the build (see docs/ux/TRACKB_REPORT.md) |
| A teacher-facing view of exactly what an ARP can see about her. | Roadmap | The pieces exist (consent switch in My class); a single screen does not |

What we do not claim: that this removes the feeling of being watched. We have not asked a teacher. It removes what we
could remove from the product itself, and a pilot should ask.

## 2d. Cascade

Training reaches teachers through a cascade (state to district to block to cluster to teacher), and each step loses some of
it. Abhyas puts one tool at each step so that every tier can see what landed without ranking anyone: the teacher practises
with a simulated child; the ARP gets a cluster meeting pack and a visit list for the teachers who agreed to share; the
trainer gets "Where training is not landing", per move, from counts only. What is not built: any measurement of how much of
a module survives each step of a real cascade. That needs real teachers and a pilot.

## 2e. Problem statement, key message by key message

The challenge brief itself is not stored in this repository. The messages below are the ones the product spec
(`spec/01_product.md`) and the problem table above take from it; if the brief words them differently, the right-hand
columns still say what exists.

| Key message | Built | Roadmap |
|---|---|---|
| Teachers get FLN training in bursts and have no safe place to practise between trainings | Rehearsal with simulated children whose answers come from a rule engine; six practice scenes (subtraction with regrouping, addition with carrying, place value, matra reading, comparing two-digit numbers, letter sound versus letter name) | More scenes; coach-approved wording (cards are still marked in review) |
| Fidelity decays: what was trained is not what is done | Explain-back with key points, rubric feedback quoting her own words, talk-move line, retry | Measuring change in classroom talk over weeks with real teachers |
| Trainers and ARPs see attendance, not adoption | Evidence ladder, ARP digest, class-visit checklist, "reported vs observed", "Where training is not landing" (latest rehearsal per teacher and move, counts only) | A real pilot and classroom observation to compare with |
| Teachers need support after training, in their language and on cheap phones | Hindi and English, voice first, taps instead of typing, light mode, under 150 KB first load, offline queue, check-in with one cited tip, next-day follow-up, daily tip (opt in), experience-aware start | Regional languages; IVR for teachers without a smartphone |
| Mixed levels and multigrade rooms | Level sorter with cited activities | Multigrade timetable support; the school-setting question |
| Teachers distrust monitoring | Opt-in sharing, support wording, the teacher sees what the ARP noted, counts only above n of 10 | A single "what can my ARP see" screen; asking teachers whether it feels different |
| Mentors are overloaded | Cluster meeting pack, visit list, escalated questions only | Time-saving measurement (none claimed) |
| Training cascades and loses content on the way | One tool per tier (see 2d) | Cascade fidelity measurement |
| Low or no connectivity | Low-network mode, offline queue, text before audio | Verified runs on real 2G devices (see the phone checklist) |

## 3. Judge Q&A (short, honest)

**Why would a teacher keep using it?** We do not know yet. The design bets on what the UP field trial says went wrong: two-minute flows, taps not typing, official sources shown on every tip, and use anchored in a cluster meeting. A pilot would measure whether teachers come back in week 3 and finish check-ins, not whether they say they like it.

**Hasn't a WhatsApp chatbot already failed in UP?** The CSBC/Ashoka trial (about 1,900 grade 3 teachers, Sitapur and Hardoi) found that neither a WhatsApp chatbot nor micro-videos improved adoption, knowledge or valuation across the sample, and only 15-20% stayed consistently active. We take that as the brief: a chat alone is not the product. We add practice with a simulated child, closed-list flows that take about two minutes, citations from official material, and a mentor-facing meeting pack. We have not shown that this does better. The web app is the channel under test; WhatsApp is built but unverified live.

**Does it improve learning?** We make no such claim and have no data. No real teacher has used the system. A pilot would measure adoption (do teachers return, finish check-ins, practise) and classroom practice (does the way they ask questions change, as observed by the ARP), not learning outcomes.

**What about multigrade classrooms?** The level sorter splits a class into 2-3 groups with one cited activity each. For reading it adds a line from the UP Class 1 handbook about classes 1 and 2 sharing a room. For maths no stored passage says it, so we say nothing. It is a planning aid, not a multigrade timetable.

**What if the AI is wrong?** The children's answers never come from a language model; a rule engine decides them, and tests enforce it. Every model output is checked by a guard, retried once, then replaced by a fixed template. Tips and activities come only from stored handbook chunks with their pages, and the system says "not available yet" when there is none. Remaining risk: the model that tags what the teacher did can mis-tag an unusual sentence, and the two UP handbooks were machine-read from images and not yet human-checked (`docs/QA_SHEET.md`).

**How does it scale to other states and languages?** A state pack is a manifest entry, two label lines and an ingestion run (`docs/ux/V2_DESIGN.md`, section 5); retrieval and citations pick it up. Languages: Hindi and English today; regional languages are on the roadmap, not built. The hosted demo is one process on a free plan and is not built to scale out (`docs/QA_SHEET.md`, question 8).

**What does it cost per teacher?** Not measured. The one real figure: about US$0.125 of Claude spend for 10 rehearsal scenes including coach feedback, about US$0.0125 a scene (`eval/one_on_one/LIVE_REPORT.md`). Speech and hosting per teacher are not measured.
