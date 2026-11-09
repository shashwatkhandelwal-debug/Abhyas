# Judge Demo Script: 15-Minute Evaluation Walkthrough

Welcome to **Abhyas**, an AI-powered voice-first practice partner for foundational learning (Classes 1–3 FLN) primary teachers in Hindi.

> [!NOTE]
> **Deterministic Children Principle**: Language models coach, classify, and cite. But **a pure deterministic rule engine decides what simulated children answer**. No LLM ever invents a child's response.

---

## 1. Credentials and Setup

- **Live URL**: Hosted instance link provided in submission form (`/login`).
- **Health Check**: `/healthz` (returns `{"status": "ok"}`). If waking from cold start, allow ~30–45 seconds.
- **Dedicated Judge Accounts**:
  - Teacher Rehearsal: `judge.1`, `judge.2`, `judge.3`, `judge.4`, `judge.5` (Independent accounts; testing will not collide).
  - Cluster Oversight (ARP): `judge.arp` (`/arp`)
  - District Oversight (Trainer / DIET): `judge.trainer` (`/trainer`)
  - AI Score Review: `judge.coach` (`/review`)
- **Password**: Provided in hackathon submission form (read dynamically from `JUDGE_PASSWORD` / `DEMO_PASSWORD` env var).

---

## 2. Five-Step Evaluation Flow (15 Minutes)

### Step 1: Voice or Text Practice with Ravi (Minutes 0–4)
1. Log in as `judge.1` (or your assigned judge number) and open `/teacher`.
2. Notice you start inside a live rehearsal on **Two-digit subtraction with regrouping (43 − 27)** with 7-year-old **Ravi**.
3. Send text or tap the microphone to speak in Hindi:
   > *"रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"*
4. **Observe**: Ravi explains his mental misconception: he subtracted the smaller digit from the larger digit in each column ($7 - 3 = 4$, $4 - 2 = 2 \rightarrow 24$).

### Step 2: Test Rule Engine Determinism & Relapse (Minutes 4–7)
1. **The "Tell the Answer" Anti-Pattern**: Teachers often get frustrated and tell the child the answer. Test this:
   > *"रवि, सही उत्तर 16 है, कॉपी में 16 लिख लो।"*
2. **Observe**: Ravi mechanically agrees (*"जी मैम, 16 लिख दिया"*).
3. Now give him a fresh transfer problem:
   > *"अब अगला सवाल करो: 61 में से 28 घटाओ।"*
4. **Observe the Relapse**: Ravi relapses immediately to the exact same bug rule: $8 - 1 = 7$, $6 - 2 = 4 \rightarrow 47$. **No LLM generated this**; the deterministic state machine enforces pedagogical reality.

### Step 3: Scaffolding and Rubric Feedback (Minutes 7–10)
1. Guide Ravi with concrete manipulatives:
   > *"रवि, 10-10 के बंडल और खुली तीलियाँ लो। 1 बंडल खोलकर 11 इकाइयाँ बनाओ।"*
2. **Observe**: Ravi successfully regroups and arrives at the correct answer (33).
3. Tap **"अभ्यास समाप्त करें" (End Practice)**.
4. **Observe Coach Feedback**: The coach evaluates your turns against the FLN Rubric (Empathy, Diagnosis, Concrete Scaffolding), quotes your exact words, and shows an exemplar demonstration from a model teacher.

### Step 4: Handbook Q&A with Honest Guardrails (Minutes 10–12)
1. Tap the **"मार्गदर्शिका से पूछें" (Ask Handbook)** chip or type a pedagogical question:
   > *"कक्षा 2 में हासिल वाली घटाव सिखाने का सही क्रम क्या है?"*
2. **Observe**: Vector search retrieves NIPUN Bharat UP Sandarshika guidelines with exact page citations.
3. Test an out-of-scope query:
   > *"आज का मौसम कैसा रहेगा?"*
4. **Observe Honest Fallback**: The Guide politely states this is outside foundational pedagogy scope and escalates to the ARP if needed. Zero hallucinations.

### Step 5: Privacy Design & Oversight (Minutes 12–15)
1. Log out and log in as `judge.arp` at `/arp`.
2. **Privacy Audit**: Notice that **teacher practice is never shown by individual teacher name**.
3. **School-Level Aggregation**: Results are grouped by school with an explicit **$n < 10$ suppression threshold** to protect teacher psychological safety.
4. Log in as `judge.trainer` at `/trainer` to view district-wide module completion rates and common classroom struggles.

---

## 3. Offline & Low-Connectivity Verification (Bonus)

1. Open `/offline.html` or toggle offline in browser DevTools.
2. Verify that the **Classroom 4-Step Checklist** works with local progress saving (`localStorage`).
3. Verify that the **Saved Rehearsal Transcripts** and **Guide Q&A** tabs display cached turns from IndexedDB without internet access.
