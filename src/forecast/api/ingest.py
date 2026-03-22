from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory
from forecast.ingest.webscrape import scrape_source

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def enqueue_dataset_processing(dataset_id: str) -> None:
    from forecast.tasks.pipeline import enqueue_dataset_processing as queue_dataset_processing

    await queue_dataset_processing(dataset_id)


@router.post("")
async def post_ingest(
    file: UploadFile | None = File(default=None),
    endpoint_url: str | None = Form(default=None),
    webscrape_url: str | None = Form(default=None),
    transcript_text: str | None = Form(default=None),
    scrape_targets: str | None = Form(default=None),
    label: str | None = Form(default=None),
) -> dict[str, str]:
    endpoint_value = endpoint_url.strip() if endpoint_url and endpoint_url.strip() else None
    webscrape_value = webscrape_url.strip() if webscrape_url and webscrape_url.strip() else None
    transcript_value = transcript_text.strip() if transcript_text and transcript_text.strip() else None

    provided_inputs = [bool(file), bool(endpoint_value), bool(webscrape_value), bool(transcript_value)]
    if sum(provided_inputs) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of file, endpoint_url, webscrape_url, or transcript_text.",
        )

    repository = DatasetRepository()
    session_factory = get_session_factory()

    if file is not None:
        raw_bytes = await file.read()
        raw_input = raw_bytes.decode("utf-8", errors="ignore")
        source_ref = label or file.filename or "uploaded-file"
        input_type = "csv"
    elif webscrape_value:
        source_url = webscrape_value
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
    elif transcript_value:
        source_ref = label.strip() if label and label.strip() else "Interview transcript"
        input_type = "transcript"
        raw_input = "\n".join(
            [
                "SOURCE TYPE: interview transcript",
                f"SOURCE LABEL: {source_ref}",
                "",
                transcript_value,
            ]
        )
    else:
        raw_input = endpoint_value or ""
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
