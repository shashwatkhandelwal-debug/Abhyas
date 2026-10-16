"""Inter-rater agreement for coach calibration (spec/11 §11.4, T42).

Quadratic-weighted (ordinal rubric 0-2) and unweighted (explain-back statuses)
Cohen's kappa, bootstrap 95% CI, exact agreement and confusion matrices, plus an
honest markdown report. Pure standard library, so it runs anywhere; the maths is
cross-checked against an independent identity and, when installed, scikit-learn.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

Label = int | str
Weights = Literal["quadratic"] | None
Pair = tuple[str, str]

DEFAULT_TARGET_KAPPA = 0.70
DEFAULT_MIN_N = 20
_MIN_VALID_BOOTSTRAPS = 20


def _check(a: Sequence[Label], b: Sequence[Label]) -> None:
    if len(a) != len(b):
        raise ValueError(f"rating lists differ in length: {len(a)} vs {len(b)}")
    if not a:
        raise ValueError("no ratings to compare")


def _labels(a: Sequence[Label], b: Sequence[Label], labels: Sequence[Label] | None) -> list[Label]:
    if labels is not None:
        return list(labels)
    return sorted(set(a) | set(b), key=lambda x: (isinstance(x, str), x))


def confusion_matrix(
    a: Sequence[Label], b: Sequence[Label], labels: Sequence[Label]
) -> list[list[int]]:
    """Counts with rater `a` on rows and rater `b` on columns, in `labels` order."""
    _check(a, b)
    index = {label: i for i, label in enumerate(labels)}
    size = len(labels)
    matrix = [[0] * size for _ in range(size)]
    for x, y in zip(a, b, strict=True):
        if x not in index or y not in index:
            raise ValueError(f"rating {x!r} or {y!r} is not in labels {list(labels)!r}")
        matrix[index[x]][index[y]] += 1
    return matrix


def exact_agreement(a: Sequence[Label], b: Sequence[Label]) -> float:
    _check(a, b)
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def _weight(i: int, j: int, size: int, weights: Weights) -> float:
    if weights is None:
        return 0.0 if i == j else 1.0
    if weights == "quadratic":
        return 0.0 if size == 1 else ((i - j) / (size - 1)) ** 2
    raise ValueError(f"unknown weights: {weights!r}")


def cohen_kappa(
    a: Sequence[Label],
    b: Sequence[Label],
    labels: Sequence[Label] | None = None,
    weights: Weights = None,
) -> float | None:
    """Cohen's kappa; `labels` must be in ordinal order for quadratic weights.

    Returns None when kappa is undefined (no expected disagreement, e.g. both
    raters used a single identical label throughout).
    """
    _check(a, b)
    labs = _labels(a, b, labels)
    size = len(labs)
    observed = confusion_matrix(a, b, labs)
    n = len(a)
    rows = [sum(row) for row in observed]
    cols = [sum(observed[i][j] for i in range(size)) for j in range(size)]
    disagreement_observed = 0.0
    disagreement_expected = 0.0
    for i in range(size):
        for j in range(size):
            w = _weight(i, j, size, weights)
            disagreement_observed += w * observed[i][j]
            disagreement_expected += w * rows[i] * cols[j] / n
    if disagreement_expected == 0:
        return None
    return 1.0 - disagreement_observed / disagreement_expected


def bootstrap_ci(
    a: Sequence[Label],
    b: Sequence[Label],
    labels: Sequence[Label] | None = None,
    weights: Weights = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile bootstrap CI over items; None if too few resamples have a defined kappa."""
    _check(a, b)
    labs = _labels(a, b, labels)
    rng = random.Random(seed)
    n = len(a)
    stats: list[float] = []
    for _ in range(n_boot):
        picks = [rng.randrange(n) for _ in range(n)]
        kappa = cohen_kappa([a[i] for i in picks], [b[i] for i in picks], labs, weights)
        if kappa is not None:
            stats.append(kappa)
    if len(stats) < max(_MIN_VALID_BOOTSTRAPS, n_boot // 10):
        return None
    stats.sort()
    low = stats[int(alpha / 2 * len(stats))]
    high = stats[min(len(stats) - 1, int((1 - alpha / 2) * len(stats)))]
    return low, high


@dataclass(frozen=True, slots=True)
class AgreementResult:
    n: int
    kappa: float | None
    ci: tuple[float, float] | None
    exact: float
    labels: tuple[Label, ...]
    confusion: tuple[tuple[int, ...], ...]


def agreement(
    a: Sequence[Label],
    b: Sequence[Label],
    labels: Sequence[Label] | None = None,
    weights: Weights = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> AgreementResult:
    labs = _labels(a, b, labels)
    return AgreementResult(
        n=len(a),
        kappa=cohen_kappa(a, b, labs, weights),
        ci=bootstrap_ci(a, b, labs, weights, n_boot=n_boot, seed=seed),
        exact=exact_agreement(a, b),
        labels=tuple(labs),
        confusion=tuple(tuple(row) for row in confusion_matrix(a, b, labs)),
    )


def pairwise_agreement(
    ratings: Mapping[str, Mapping[str, Label]],
    labels: Sequence[Label],
    weights: Weights = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[Pair, AgreementResult]:
    """Agreement for every rater pair (e.g. 'ai' vs each coach, coach vs coach).

    `ratings[rater][item_id]` is one label; only items both raters rated are used.
    """
    results: dict[Pair, AgreementResult] = {}
    for first, second in combinations(sorted(ratings), 2):
        shared = sorted(set(ratings[first]) & set(ratings[second]))
        if not shared:
            continue
        results[(first, second)] = agreement(
            [ratings[first][item] for item in shared],
            [ratings[second][item] for item in shared],
            labels,
            weights,
            n_boot=n_boot,
            seed=seed,
        )
    return results


def criterion_agreement(
    ratings: Mapping[str, Mapping[str, Mapping[str, Label]]],
    labels: Sequence[Label],
    weights: Weights = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, dict[Pair, AgreementResult]]:
    """Per-criterion pairwise agreement from `ratings[rater][item_id][criterion]`."""
    criteria = sorted(
        {c for items in ratings.values() for scores in items.values() for c in scores}
    )
    out: dict[str, dict[Pair, AgreementResult]] = {}
    for criterion in criteria:
        per_rater = {
            rater: {
                item: scores[criterion] for item, scores in items.items() if criterion in scores
            }
            for rater, items in ratings.items()
        }
        out[criterion] = pairwise_agreement(per_rater, labels, weights, n_boot=n_boot, seed=seed)
    return out


def _fmt(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.2f}"


def render_report(
    title: str,
    results: Mapping[str, Mapping[Pair, AgreementResult]],
    *,
    target: float = DEFAULT_TARGET_KAPPA,
    min_n: int = DEFAULT_MIN_N,
) -> str:
    """Markdown report. Always states n and flags weak results; never hides them."""
    lines = [f"# {title}", "", "| Criterion | Raters | n | kappa | 95% CI | Exact agreement |"]
    lines.append("|---|---|---|---|---|---|")
    warnings: list[str] = []
    for criterion, pairs in results.items():
        for (first, second), res in pairs.items():
            ci = "n/a" if res.ci is None else f"{res.ci[0]:.2f} to {res.ci[1]:.2f}"
            lines.append(
                f"| {criterion} | {first} vs {second} | {res.n} | {_fmt(res.kappa)} | {ci} "
                f"| {res.exact:.0%} |"
            )
            where = f"{criterion} ({first} vs {second})"
            if res.n < min_n:
                warnings.append(
                    f"{where}: n={res.n} is below the target of {min_n}; treat as indicative."
                )
            if res.kappa is None:
                warnings.append(f"{where}: kappa is undefined (no variation in ratings).")
            elif res.kappa < target:
                warnings.append(f"{where}: kappa {res.kappa:.2f} is below the {target:.2f} target.")
    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in warnings] or ["- None."]
    lines += ["", "## Confusion matrices (rows = first rater, columns = second rater)", ""]
    for criterion, pairs in results.items():
        for (first, second), res in pairs.items():
            header = " | ".join(str(label) for label in res.labels)
            lines += [f"**{criterion}, {first} vs {second}**", "", f"| | {header} |"]
            lines.append("|---|" + "---|" * len(res.labels))
            for label, row in zip(res.labels, res.confusion, strict=True):
                lines.append(f"| {label} | " + " | ".join(str(c) for c in row) + " |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
