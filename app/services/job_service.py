
import copy
import json
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.services.pipeline_service import (
    process_video,
    validate_pipeline_settings,
)


BASE_DIR = Path(__file__).resolve().parent.parent.parent

UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
JOBS_DIR = BASE_DIR / "storage" / "jobs"

JOBS_DIR.mkdir(parents=True, exist_ok=True)

# One worker prevents simultaneous CPU-heavy pipelines.
EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="clipmind-worker"
)

LOCK = threading.RLock()

JOBS = {}


def utc_now():
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def save_job(job):
    """
    Save a job status snapshot to disk.

    Caller must hold LOCK.
    """
    path = JOBS_DIR / f"{job['job_id']}.json"
    temporary_path = JOBS_DIR / f"{job['job_id']}.json.tmp"

    with open(
        temporary_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            job,
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_path.replace(path)


def get_job(job_id):
    """
    Return a safe copy of a job's current status.
    """
    with LOCK:
        job = JOBS.get(job_id)

        if job is None:
            return None

        return copy.deepcopy(job)


def list_jobs():
    """
    Return job summaries, newest first.
    """
    with LOCK:
        jobs = [
            {
                "job_id": job["job_id"],
                "status": job["status"],
                "stage": job["stage"],
                "progress": job["progress"],
                "message": job["message"],
                "created_at": job["created_at"]
            }
            for job in JOBS.values()
        ]

    return sorted(
        jobs,
        key=lambda item: item["created_at"],
        reverse=True
    )


def update_job(job_id, **changes):
    """
    Update job state and save it safely.
    """
    with LOCK:
        job = JOBS.get(job_id)

        if job is None:
            return

        job.update(changes)
        job["updated_at"] = utc_now()

        save_job(job)


def run_job(job_id):
    """
    Execute a queued job in the background worker.
    """
    with LOCK:
        job = JOBS.get(job_id)

        if job is None:
            return

        video_path = job["video_path"]
        settings = copy.deepcopy(job["settings"])

    update_job(
        job_id,
        status="processing",
        stage="initializing",
        progress=0,
        message="Starting video processing...",
        started_at=utc_now()
    )

    def on_progress(update):
        update_job(
            job_id,
            status=update["status"],
            stage=update["stage"],
            progress=update["progress"],
            message=update["message"]
        )

    try:
        result = process_video(
            video_path=video_path,
            clip_count=settings["clip_count"],
            min_duration=settings["min_duration"],
            max_duration=settings["max_duration"],
            vertical_mode=settings["vertical_mode"],
            caption_style=settings["caption_style"],
            width=settings["width"],
            height=settings["height"],
            progress_callback=on_progress,
            enable_captions=settings.get("enable_captions", False)
        )

        update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message=(
                "Your captioned Shorts are ready!"
                if settings.get("enable_captions", False)
                else "Your Shorts are ready!"
            ),
            completed_at=utc_now(),
            result={
                "report_path": result["report_path"],
                "generated_clips": result["generated_clips"],
                "processing_time_seconds": (
                    result["processing_time_seconds"]
                ),
                "clips": result["clips"]
            }
        )

    except Exception as error:
        update_job(
            job_id,
            status="failed",
            stage=getattr(error, "stage", "unknown"),
            message=str(error),
            completed_at=utc_now(),
            error=str(error)
        )


def create_job(
    video_filename,
    clip_count=5,
    min_duration=20,
    max_duration=30,
    vertical_mode="blur_background",
    caption_style="word_highlight",
    width=720,
    height=1280,
    enable_captions=False
):
    """
    Validate the request, create a job,
    and submit it to the background worker.
    """

    # Only allow a filename, never a directory path.
    if (
        not isinstance(video_filename, str)
        or not video_filename
        or Path(video_filename).name != video_filename
        or "/" in video_filename
        or "\\" in video_filename
    ):
        raise ValueError("Invalid video filename.")

    video_path = UPLOAD_DIR / video_filename

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Uploaded video not found: {video_filename}"
        )

    validate_pipeline_settings(
        clip_count=clip_count,
        min_duration=min_duration,
        max_duration=max_duration,
        vertical_mode=vertical_mode,
        caption_style=caption_style,
        width=width,
        height=height
    )

    settings = {
        "clip_count": clip_count,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "vertical_mode": vertical_mode,
        "caption_style": caption_style,
        "enable_captions": enable_captions,
        "width": width,
        "height": height
    }

    job_id = uuid.uuid4().hex
    timestamp = utc_now()

    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Waiting for background worker...",
        "video_filename": video_filename,
        "video_path": str(video_path),
        "settings": settings,
        "created_at": timestamp,
        "updated_at": timestamp,
        "started_at": None,
        "completed_at": None,
        "error": None,
        "result": None
    }

    with LOCK:
        JOBS[job_id] = job
        save_job(job)

    try:
        EXECUTOR.submit(run_job, job_id)
    except Exception:
        update_job(
            job_id,
            status="failed",
            stage="queue",
            message="Could not start background worker.",
            error="Background worker unavailable.",
            completed_at=utc_now()
        )
        raise

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Video processing job created."
    }


def load_previous_jobs():
    """
    Load saved jobs when the application starts.

    Jobs interrupted by shutdown cannot resume
    automatically in this version.
    """

    loaded_count = 0

    with LOCK:
        for path in JOBS_DIR.glob("*.json"):
            try:
                with open(
                    path,
                    "r",
                    encoding="utf-8"
                ) as file:
                    job = json.load(file)

                job_id = job["job_id"]

                if job["status"] in (
                    "queued",
                    "processing"
                ):
                    job["status"] = "interrupted"
                    job["stage"] = "interrupted"
                    job["message"] = (
                        "Processing was interrupted "
                        "by application shutdown."
                    )
                    job["updated_at"] = utc_now()
                    save_job(job)

                JOBS[job_id] = job
                loaded_count += 1

            except Exception as error:
                print(
                    f"Could not load job {path.name}: "
                    f"{error}"
                )

    return loaded_count


# Restore saved job history when imported.
load_previous_jobs()
