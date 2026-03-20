from __future__ import annotations

from typing import Dict, Optional


def compute_stage2_metrics(lead_track: Optional[str], backing_count: int) -> Dict[str, object]:
    """Compute lightweight stage2 metrics placeholder."""
    return {
        "has_lead": bool(lead_track),
        "backing_count": max(0, int(backing_count or 0)),
    }
