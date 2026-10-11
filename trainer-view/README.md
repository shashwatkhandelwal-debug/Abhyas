# Trainer View (`trainer-view/`)

Read-only web view for DIET (District Institute of Education and Training) and SCERT trainers to view training adoption metrics by module and training batch.

## Privacy & Suppression Guarantee (§0, §12, §13)
- Aggregates metrics only for groups where $n \ge 10$.
- Any cohort, school, or cluster with fewer than 10 teachers is strictly suppressed from upward reporting.
- Displays adoption fidelity (e.g., missing explanation points, rubric distribution, evidence ladder) rather than mere attendance.
