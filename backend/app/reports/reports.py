"""Phase 17: reports/exports. See PRODUCT_SPEC.md §9's exit criteria --
"CSV/XLSX/JSON/PDF export for each report type." `generate_report()` is
the one entry point the API layer calls: it looks up the right row
builder (app/reports/rows.py) and column set for `report_type`, then
hands the rows to the right writer (app/reports/export.py) for
`export_format`. Every value in every report traces back to a row this
project already collected and verified elsewhere -- this module adds no
new computation.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.reports import export, rows

REPORT_TYPES = ("backlinks", "link_gaps", "contacts", "guest_posts", "opportunity_scores")
EXPORT_FORMATS = ("csv", "json", "xlsx", "pdf")


@dataclass
class _ReportSpec:
    build_rows: Callable[..., list[dict]]
    columns: list[str]
    accepted_filters: set[str]  # kwargs build_rows actually accepts
    required_filter: str = ""  # the one filter this report type can't run without


_SPECS: dict[str, _ReportSpec] = {
    "backlinks": _ReportSpec(
        build_rows=rows.backlinks_rows,
        columns=[
            "id",
            "source_url",
            "target_url",
            "source_host",
            "target_host",
            "anchor_text",
            "link_type",
            "rel_nofollow",
            "rel_sponsored",
            "rel_ugc",
            "first_seen_at",
            "last_seen_at",
            "lost_at",
        ],
        accepted_filters={"target_domain_id", "source_domain_id"},
    ),
    "link_gaps": _ReportSpec(
        build_rows=rows.link_gap_rows,
        columns=[
            "id",
            "candidate_host",
            "competitor_overlap_count",
            "confidence",
            "evidence",
            "computed_at",
        ],
        accepted_filters={"primary_domain_id"},
        required_filter="primary_domain_id",
    ),
    "contacts": _ReportSpec(
        build_rows=rows.contacts_rows,
        columns=[
            "id",
            "domain_host",
            "name",
            "job_title",
            "email",
            "phone",
            "verification_status",
            "confidence_score",
        ],
        accepted_filters={"domain_id"},
        required_filter="domain_id",
    ),
    "guest_posts": _ReportSpec(
        build_rows=rows.guest_post_rows,
        columns=[
            "id",
            "domain_host",
            "guideline_page_url",
            "editor_email",
            "word_count_min",
            "word_count_max",
            "appears_closed",
            "distinct_authors_observed",
            "guest_post_probability",
            "evidence",
            "computed_at",
        ],
        accepted_filters={"domain_id"},
    ),
    "opportunity_scores": _ReportSpec(
        build_rows=rows.opportunity_score_rows,
        columns=[
            "id",
            "domain_host",
            "reference_host",
            "composite_score",
            "evidence",
            "computed_at",
        ],
        accepted_filters={"domain_id", "reference_domain_id"},
    ),
}


def generate_report(
    session: Session,
    *,
    report_type: str,
    export_format: str,
    **filters: uuid.UUID | None,
) -> bytes:
    if report_type not in _SPECS:
        raise ValueError(f"unknown report type: {report_type}")
    if export_format not in EXPORT_FORMATS:
        raise ValueError(f"unsupported export format: {export_format}")

    spec = _SPECS[report_type]
    if spec.required_filter and not filters.get(spec.required_filter):
        raise ValueError(f"report type {report_type!r} requires {spec.required_filter!r}")

    accepted = {k: v for k, v in filters.items() if k in spec.accepted_filters and v is not None}
    row_data = spec.build_rows(session, **accepted)

    if export_format == "csv":
        return export.to_csv(row_data, spec.columns)
    if export_format == "json":
        return export.to_json(row_data, spec.columns)
    if export_format == "xlsx":
        return export.to_xlsx(row_data, spec.columns, title=report_type)
    return export.to_pdf(row_data, spec.columns, title=report_type.replace("_", " ").title())
