"""Build STIG Viewer–compatible CKLB JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from cklb_shape import (
    display_name,
    index_reviews,
    lookup_review,
    resolve_stig_id,
    stable_uuid,
    viewer_rule,
    viewer_target_data,
)
from models import STATUS_TO_CKLB


def export_cklb(
    checklist: Dict[str, Any],
    baseline: Dict[str, Any],
    rules: List[Dict[str, Any]],
    reviews_by_group: Any,
    host: Dict[str, Any],
) -> str:
    review_index = index_reviews(reviews_by_group)
    stig_id = resolve_stig_id(baseline)
    stig_uuid = baseline.get("uuid") or stable_uuid("stig", baseline.get("_key") or stig_id)
    shown_name = display_name(baseline)
    ref_id = baseline.get("reference_identifier") or ""

    cklb_rules: List[Dict[str, Any]] = []
    for rule in rules:
        review = lookup_review(rule, review_index)
        status = review.get("status") or "not_reviewed"
        cklb_rules.append(
            viewer_rule(
                rule,
                review,
                baseline,
                stig_uuid,
                STATUS_TO_CKLB.get(status, status),
            )
        )
        if not ref_id:
            ref_id = cklb_rules[-1].get("reference_identifier") or ""

    doc = {
        "title": checklist.get("title") or baseline.get("title") or shown_name,
        "id": checklist.get("uuid")
        or stable_uuid("checklist", checklist.get("_key") or checklist.get("id")),
        "stigs": [
            {
                "stig_name": baseline.get("stig_name") or baseline.get("title") or "",
                "display_name": shown_name,
                "stig_id": stig_id,
                "release_info": baseline.get("release_info") or "",
                "version": str(baseline.get("version") or ""),
                "uuid": stig_uuid,
                "reference_identifier": str(ref_id),
                "size": len(cklb_rules),
                "rules": cklb_rules,
            }
        ],
        "active": True,
        "mode": 2,
        "has_path": False,
        "target_data": viewer_target_data(checklist, host),
        "cklb_version": "1.0",
    }
    return json.dumps(doc, indent=2)
