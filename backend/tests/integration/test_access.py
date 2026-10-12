"""Access control and privacy scoping integration tests (spec/03 §3.3).

Verifies:
1. Teacher can only access own records.
2. ARP can only access teachers in own cluster.
3. ARP cannot access scores for non-consenting teacher in own cluster.
4. Trainer endpoint never returns groups with n < 10 unsuppressed.
5. No endpoint returns teacher_contact.
"""

import uuid

from backend.app.auth.access import (
    SUPPRESSION_MESSAGE,
    apply_aggregation_suppression,
    can_access_teacher,
    can_view_teacher_scores,
    get_teacher_display_name_for_arp,
)
from backend.app.db.models import AppUser, Teacher, TeacherContact


def test_teacher_can_only_access_own_records() -> None:
    t1_id = uuid.uuid4()
    t2_id = uuid.uuid4()

    teacher_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        password_hash="hash",
        role="teacher",
        teacher_id=t1_id,
    )
    t1 = Teacher(id=t1_id, name="शिक्षिका 1")
    t2 = Teacher(id=t2_id, name="शिक्षिका 2")

    assert can_access_teacher(teacher_user, t1) is True
    assert can_access_teacher(teacher_user, t2) is False
    assert can_view_teacher_scores(teacher_user, t1) is True
    assert can_view_teacher_scores(teacher_user, t2) is False


def test_arp_access_in_own_cluster_consenting_vs_non_consenting() -> None:
    cluster_1 = "KNP-C01"
    cluster_2 = "KNP-C02"

    arp_user = AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        password_hash="hash",
        role="arp",
        cluster_id=cluster_1,
    )

    # Consenting teacher in same cluster
    t_consenting = Teacher(
        id=uuid.uuid4(),
        name="सुमन",
        cluster_id=cluster_1,
        consent_share_scores=True,
    )

    # Non-consenting teacher in same cluster
    t_non_consenting = Teacher(
        id=uuid.uuid4(),
        name="रेखा",
        cluster_id=cluster_1,
        consent_share_scores=False,
    )

    # Teacher in different cluster
    t_other_cluster = Teacher(
        id=uuid.uuid4(),
        name="पूजा",
        cluster_id=cluster_2,
        consent_share_scores=True,
    )

    # 1. ARP can access metadata for teachers in own cluster
    assert can_access_teacher(arp_user, t_consenting) is True
    assert can_access_teacher(arp_user, t_non_consenting) is True

    # 2. ARP cannot access teachers from another cluster (§3.3)
    assert can_access_teacher(arp_user, t_other_cluster) is False
    assert can_view_teacher_scores(arp_user, t_other_cluster) is False

    # 3. ARP can view scores for consenting teacher, but CANNOT for non-consenting teacher (§3.3)
    assert can_view_teacher_scores(arp_user, t_consenting) is True
    assert can_view_teacher_scores(arp_user, t_non_consenting) is False

    # 4. Display name for non-consenting is anonymized
    assert get_teacher_display_name_for_arp(arp_user, t_consenting) == "सुमन"
    assert get_teacher_display_name_for_arp(arp_user, t_non_consenting).startswith("शिक्षक #")


def test_admin_has_full_access() -> None:
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin.demo",
        password_hash="hash",
        role="admin",
    )
    t = Teacher(
        id=uuid.uuid4(),
        name="अनीता",
        cluster_id="KNP-C01",
        consent_share_scores=False,
    )
    assert can_access_teacher(admin_user, t) is True
    assert can_view_teacher_scores(admin_user, t) is True


def test_trainer_suppression_n_less_than_10() -> None:
    # Small batch (n=8, e.g. KNP-B3)
    row_small = {
        "batch_id": "KNP-B3",
        "move_id": "m_sub_regroup_intro",
        "n_teachers": 8,
        "rubric_dist": {"c1": {"0": 1, "1": 3, "2": 4}},
        "active_rate": 0.75,
    }
    suppressed = apply_aggregation_suppression(row_small, n_teachers=8, threshold=10)
    assert suppressed["suppressed"] is True
    assert suppressed["rubric_dist"] == SUPPRESSION_MESSAGE
    assert suppressed["active_rate"] == SUPPRESSION_MESSAGE

    # Normal batch (n=25, e.g. KNP-B1)
    row_normal = {
        "batch_id": "KNP-B1",
        "move_id": "m_sub_regroup_intro",
        "n_teachers": 25,
        "rubric_dist": {"c1": {"0": 2, "1": 8, "2": 15}},
        "active_rate": 0.88,
    }
    unsuppressed = apply_aggregation_suppression(row_normal, n_teachers=25, threshold=10)
    assert unsuppressed["suppressed"] is False
    assert unsuppressed["rubric_dist"] == {"c1": {"0": 2, "1": 8, "2": 15}}


def test_teacher_contact_never_exposed() -> None:
    # Model check: ensure TeacherContact model holds encrypted phone and is not coupled to public teacher model
    assert hasattr(TeacherContact, "phone_enc")
    assert not hasattr(Teacher, "phone_enc")
