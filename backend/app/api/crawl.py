import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import CrawlJobDetailOut
from app.core.config import settings
from app.crawler.run import run_crawl
from app.db.models import CrawlError, CrawlJob, CrawlRequest, Page

router = APIRouter(tags=["crawl"])


class StartCrawlIn(BaseModel):
    url: str
    max_pages: int | None = None


@router.post("/crawl", response_model=CrawlJobDetailOut, status_code=202)
async def start_crawl(body: StartCrawlIn, db: Session = Depends(get_db)) -> CrawlJobDetailOut:
    job_id = await run_crawl(body.url, max_pages=body.max_pages or settings.crawler_max_pages_per_job)
    return _job_detail(db, job_id)


@router.get("/crawl/{job_id}", response_model=CrawlJobDetailOut)
def get_crawl_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> CrawlJobDetailOut:
    return _job_detail(db, job_id)


def _job_detail(db: Session, job_id: uuid.UUID) -> CrawlJobDetailOut:
    job = db.get(CrawlJob, job_id)
    if job is None:
        raise NotFoundError(f"no such crawl job: {job_id}")

    page_count = db.scalar(
        select(func.count())
        .select_from(Page)
        .join(CrawlRequest, Page.crawl_request_id == CrawlRequest.id)
        .where(CrawlRequest.crawl_job_id == job_id)
    )
    error_count = db.scalar(
        select(func.count()).select_from(CrawlError).where(CrawlError.crawl_job_id == job_id)
    )
    return CrawlJobDetailOut(
        **{field: getattr(job, field) for field in CrawlJobDetailOut.model_fields if hasattr(job, field)},
        page_count=page_count or 0,
        error_count=error_count or 0,
    )
