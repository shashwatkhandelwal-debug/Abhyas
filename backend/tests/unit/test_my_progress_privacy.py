"""L1c: "My progress" is for the teacher herself. No ARP, trainer, coach-review page, report builder
or CSV export reads her rehearsal history for it or carries its words.

Two checks that need no database: nobody outside the chat service imports the module or calls the
repository method, and no template, report or export source mentions its catalog keys.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "backend/app"
READERS = ("my_progress", "rehearsal_history", "_my_progress_messages")
# Where the history is allowed to be read: the module itself, the leaf record, the repository query
# and the chat service that answers her own tap (and the demo seed that writes the demo rows)
ALLOWED = {
    "class_profile/my_progress.py",
    "sessions/rehearsal_view.py",
    "sessions/repository.py",
    "sessions/service.py",
}
OTHERS = ("web", "reports", "auth", "channels", "jobs", "admin")


def sources(folder: str) -> list[Path]:
    return sorted(p for p in (APP / folder).rglob("*") if p.suffix in {".py", ".html", ".js"})


def test_nothing_outside_the_chat_service_reads_the_history() -> None:
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel in ALLOWED or rel.startswith("db/migrations"):
            continue
        text = path.read_text(encoding="utf-8")
        if any(re.search(rf"\b{name}\b", text) for name in READERS):
            offenders.append(rel)
    assert offenders == []


def test_dashboards_exports_and_the_review_console_never_name_its_keys() -> None:
    pattern = re.compile(r"\bmp_[a-z_]+\b|btn_mp_practice|class_profile\.my_progress")
    hits = [
        f"{p.relative_to(APP).as_posix()}: {m.group(0)}"
        for folder in OTHERS
        for p in sources(folder)
        for m in pattern.finditer(p.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_the_only_new_repository_read_is_scoped_to_one_teacher() -> None:
    text = (APP / "sessions/repository.py").read_text(encoding="utf-8")
    start = text.index("async def rehearsal_history")
    body = text[start : text.index("async def peer_worked_teachers")]
    assert "RehearsalScore.teacher_id == teacher_id" in body
    assert "Scene.teacher_id == teacher_id" in body and "Turn.teacher_id == teacher_id" in body
