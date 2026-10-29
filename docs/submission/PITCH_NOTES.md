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
| Regional languages via Bhashini | Roadmap | A Bhashini client file exists in the repo; the product is Hindi and English only |
| Home-language bridging scenes | Roadmap | |
| IVR for teachers without a smartphone | Roadmap | |
| A real WhatsApp pilot | Roadmap | Needs Meta credentials and teachers |
| Classroom-outcome measurement | Roadmap | No real teacher has used the system |

## 3. Judge Q&A (short, honest)

**Why would a teacher keep using it?** We do not know yet. The design bets on what the UP field trial says went wrong: two-minute flows, taps not typing, official sources shown on every tip, and use anchored in a cluster meeting. A pilot would measure whether teachers come back in week 3 and finish check-ins, not whether they say they like it.

**Hasn't a WhatsApp chatbot already failed in UP?** The CSBC/Ashoka trial (about 1,900 grade 3 teachers, Sitapur and Hardoi) found that neither a WhatsApp chatbot nor micro-videos improved adoption, knowledge or valuation across the sample, and only 15-20% stayed consistently active. We take that as the brief: a chat alone is not the product. We add practice with a simulated child, closed-list flows that take about two minutes, citations from official material, and a mentor-facing meeting pack. We have not shown that this does better. The web app is the channel under test; WhatsApp is built but unverified live.

**Does it improve learning?** We make no such claim and have no data. No real teacher has used the system. A pilot would measure adoption (do teachers return, finish check-ins, practise) and classroom practice (does the way they ask questions change, as observed by the ARP), not learning outcomes.

**What about multigrade classrooms?** The level sorter splits a class into 2-3 groups with one cited activity each. For reading it adds a line from the UP Class 1 handbook about classes 1 and 2 sharing a room. For maths no stored passage says it, so we say nothing. It is a planning aid, not a multigrade timetable.

**What if the AI is wrong?** The children's answers never come from a language model; a rule engine decides them, and tests enforce it. Every model output is checked by a guard, retried once, then replaced by a fixed template. Tips and activities come only from stored handbook chunks with their pages, and the system says "not available yet" when there is none. Remaining risk: the model that tags what the teacher did can mis-tag an unusual sentence, and the two UP handbooks were machine-read from images and not yet human-checked (`docs/QA_SHEET.md`).

**How does it scale to other states and languages?** A state pack is a manifest entry, two label lines and an ingestion run (`docs/ux/V2_DESIGN.md`, section 5); retrieval and citations pick it up. Languages: Hindi and English today; regional languages are on the roadmap, not built. The hosted demo is one process on a free plan and is not built to scale out (`docs/QA_SHEET.md`, question 8).

**What does it cost per teacher?** Not measured. The one real figure: about US$0.125 of Claude spend for 10 rehearsal scenes including coach feedback, about US$0.0125 a scene (`eval/one_on_one/LIVE_REPORT.md`). Speech and hosting per teacher are not measured.
