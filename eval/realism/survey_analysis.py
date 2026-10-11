"""Realism survey analysis for simulated child interactions (§15).

Target: >= 4 of 5 average teacher rating on post-rehearsal realism.
"""

from typing import Sequence


def analyze_realism_ratings(ratings: Sequence[int]) -> dict[str, float]:
    if not ratings:
        return {"mean": 0.0, "pct_four_or_above": 0.0}
    mean_val = sum(ratings) / len(ratings)
    pct_four = (sum(1 for r in ratings if r >= 4) / len(ratings)) * 100.0
    return {
        "mean": round(mean_val, 2),
        "pct_four_or_above": round(pct_four, 1),
    }


if __name__ == "__main__":
    sample_ratings = [4, 5, 4, 4, 3, 5, 4, 5, 4, 4, 5, 3, 4, 5]
    res = analyze_realism_ratings(sample_ratings)
    print(f"Average Realism Rating: {res['mean']} / 5")
    print(f"Teachers Rating >= 4: {res['pct_four_or_above']}%")
