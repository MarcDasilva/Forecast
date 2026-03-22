from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory
from forecast.ingest.webscrape import scrape_source
from forecast.tasks.pipeline import enqueue_dataset_processing

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("")
async def post_ingest(
    file: UploadFile | None = File(default=None),
    endpoint_url: str | None = Form(default=None),
    webscrape_url: str | None = Form(default=None),
    scrape_targets: str | None = Form(default=None),
    label: str | None = Form(default=None),
) -> dict[str, str]:
    provided_inputs = [bool(file), bool(endpoint_url), bool(webscrape_url)]
    if sum(provided_inputs) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of file, endpoint_url, or webscrape_url.",
        )

    repository = DatasetRepository()
    session_factory = get_session_factory()

    if file is not None:
        raw_bytes = await file.read()
        raw_input = raw_bytes.decode("utf-8", errors="ignore")
        source_ref = label or file.filename or "uploaded-file"
        input_type = "csv"
    elif webscrape_url:
        source_url = webscrape_url.strip()
        raw_input, derived_targets, _ = scrape_source(
            source_url=source_url,
            label=label,
            scrape_targets=scrape_targets,
        )
        source_ref = label or source_url
        input_type = "webscrape"
        if not label:
            source_ref = source_url
        raw_input = "\n".join(
            [
                raw_input,
                f"SOURCE LABEL: {label.strip()}" if label and label.strip() else f"SOURCE LABEL: {source_ref}",
                f"DERIVED TARGETS: {', '.join(derived_targets)}",
            ]
        )
    else:
        raw_input = endpoint_url.strip() if endpoint_url else ""
        source_ref = label or raw_input
        input_type = "endpoint"

    async with session_factory() as session:
        async with session.begin():
            dataset = await repository.create_dataset(
                session,
                input_type=input_type,
                source_ref=source_ref,
                raw_text=raw_input,
                status="pending",
            )

    await enqueue_dataset_processing(str(dataset.id))

    return {
        "dataset_id": str(dataset.id),
        "status": "pending",
        "message": "Dataset queued for processing.",
    }
