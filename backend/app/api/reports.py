import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.reports.export import content_type_for
from app.reports.reports import generate_report

router = APIRouter(prefix="/reports", tags=["reports"])

_EXTENSIONS = {"csv": "csv", "json": "json", "xlsx": "xlsx", "pdf": "pdf"}


@router.get("/{report_type}")
def get_report(
    report_type: str,
    format: str = Query(default="csv"),
    target_domain_id: uuid.UUID | None = Query(default=None),
    source_domain_id: uuid.UUID | None = Query(default=None),
    primary_domain_id: uuid.UUID | None = Query(default=None),
    domain_id: uuid.UUID | None = Query(default=None),
    reference_domain_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """Every value in every report traces back to a row this project
    already collected and verified elsewhere -- see
    app/reports/reports.py. `format` is one of csv/json/xlsx/pdf.
    """
    try:
        body = generate_report(
            db,
            report_type=report_type,
            export_format=format,
            target_domain_id=target_domain_id,
            source_domain_id=source_domain_id,
            primary_domain_id=primary_domain_id,
            domain_id=domain_id,
            reference_domain_id=reference_domain_id,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc

    extension = _EXTENSIONS[format]
    filename = f"{report_type}.{extension}"
    return Response(
        content=body,
        media_type=content_type_for(format),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
