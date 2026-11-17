
from pathlib import Path
import re
import subprocess
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.services.video_service import get_video_metadata
from app.services.youtube_service import (
    validate_youtube_url,
    download_youtube_video,
)
from app.services.job_service import (
    create_job,
    get_job,
    list_jobs,
)


app = FastAPI(
    title="ClipMind AI",
    description="AI-powered video clipping application",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_FILE = BASE_DIR / "frontend" / "index.html"
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
OUTPUT_DIR = (BASE_DIR / "storage" / "output").resolve()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 500 * 1024 * 1024

ALLOWED_FORMATS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm"
}


class ProcessingRequest(BaseModel):
    video_filename: str
    clip_count: int = Field(default=5, ge=1, le=20)
    min_duration: float = Field(default=20, ge=5, le=120)
    max_duration: float = Field(default=30, ge=5, le=120)
    vertical_mode: str = "blur_background"
    caption_style: str = "word_highlight"
    width: int = 720
    height: int = 1280
    enable_captions: bool = False


class YouTubeImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@app.get("/")
def home():
    return FileResponse(FRONTEND_FILE)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "application": "ClipMind AI"
    }


# --------------------------------------------------
# Local video upload
# --------------------------------------------------

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename provided"
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format"
        )

    unique_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / unique_name
    total_size = 0

    try:
        with open(file_path, "wb") as video:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds 500 MB limit"
                    )

                video.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty"
            )

        try:
            metadata = await run_in_threadpool(
                get_video_metadata,
                str(file_path)
            )

        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="FFprobe or uploaded video file not found"
            )

        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail="Video analysis timed out"
            )

        except Exception:
            raise HTTPException(
                status_code=422,
                detail="Video analysis failed. Please upload a valid video."
            )

        if not metadata.get("video_codec"):
            raise HTTPException(
                status_code=422,
                detail="No video stream found in uploaded file"
            )

        return {
            "status": "success",
            "message": "Video uploaded and analyzed successfully!",
            "original_filename": file.filename,
            "saved_filename": unique_name,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "metadata": metadata
        }

    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise

    finally:
        await file.close()


# --------------------------------------------------
# YouTube video import
# --------------------------------------------------

@app.post("/api/youtube/import")
async def import_youtube_video(request: YouTubeImportRequest):
    """
    Import an authorized YouTube video into local storage.

    This endpoint imports the source video only.
    It does not automatically start AI processing.
    """

    try:
        clean_url = validate_youtube_url(request.url)

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    try:
        # Downloading is blocking I/O, so run it outside
        # FastAPI's event loop.
        result = await run_in_threadpool(
            download_youtube_video,
            clean_url
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        print(f"YouTube import failed: {error}")

        raise HTTPException(
            status_code=502,
            detail=(
                "YouTube import failed. The video may be "
                "unavailable, restricted, or unsupported."
            )
        )

    saved_filename = result.get("saved_filename")

    if not saved_filename:
        raise HTTPException(
            status_code=500,
            detail="YouTube import did not return a filename."
        )

    video_path = (UPLOAD_DIR / saved_filename).resolve()

    if not video_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=500,
            detail="Invalid imported video path."
        )

    if not video_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="Imported video file was not found."
        )

    if video_path.stat().st_size > MAX_FILE_SIZE:
        video_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=413,
            detail="Imported video exceeds the 500 MB limit."
        )

    try:
        metadata = await run_in_threadpool(
            get_video_metadata,
            str(video_path)
        )

        if not metadata.get("video_codec"):
            raise ValueError(
                "Imported file does not contain a video stream."
            )

    except Exception as error:
        print(f"Imported video analysis failed: {error}")

        video_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail="Imported video could not be analyzed."
        )

    return {
        "status": "success",
        "message": "YouTube video imported successfully!",
        "source": "youtube",
        "youtube_id": result.get("youtube_id"),
        "title": result.get("title"),
        "original_filename": result.get("title"),
        "saved_filename": saved_filename,
        "size_mb": result.get("size_mb"),
        "metadata": metadata
    }


# --------------------------------------------------
# Start AI processing
# --------------------------------------------------

@app.post("/api/process", status_code=202)
def start_processing(request: ProcessingRequest):
    try:
        return create_job(
            video_filename=request.video_filename,
            clip_count=request.clip_count,
            min_duration=request.min_duration,
            max_duration=request.max_duration,
            vertical_mode=request.vertical_mode,
            caption_style=request.caption_style,
            width=request.width,
            height=request.height,
            enable_captions=request.enable_captions
        )

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        print(f"Could not create processing job: {error}")

        raise HTTPException(
            status_code=500,
            detail="Could not start processing job."
        )


# --------------------------------------------------
# Job history and status
# --------------------------------------------------

@app.get("/api/jobs")
def get_all_jobs():
    return {"jobs": list_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Processing job not found."
        )

    return job


# --------------------------------------------------
# Secure completed clip lookup
# --------------------------------------------------

def find_completed_clip(job_id: str, clip_id: int):
    """
    Find a clip belonging to a completed job.

    Never accept arbitrary file paths from API callers.
    """

    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(
            status_code=404,
            detail="Processing job not found."
        )

    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Processing job not found."
        )

    if job.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail="Processing job is not completed."
        )

    result = job.get("result")

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=404,
            detail="Job results not found."
        )

    clips = result.get("clips", [])

    for clip in clips:
        try:
            matches = int(clip.get("clip_id")) == clip_id
        except (ValueError, TypeError):
            continue

        if not matches:
            continue

        stored_path = clip.get("file_path")

        if not isinstance(stored_path, str) or not stored_path:
            raise HTTPException(
                status_code=404,
                detail="Clip file path is missing."
            )

        file_path = Path(stored_path).resolve()

        # Restrict access to this application's output folder.
        if not file_path.is_relative_to(OUTPUT_DIR):
            raise HTTPException(
                status_code=403,
                detail="Clip file access denied."
            )

        if file_path.suffix.lower() != ".mp4":
            raise HTTPException(
                status_code=403,
                detail="Only MP4 clips can be served."
            )

        if not file_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Generated clip file not found."
            )

        return file_path

    raise HTTPException(
        status_code=404,
        detail="Clip not found in this job."
    )


# --------------------------------------------------
# Play a generated Short
# --------------------------------------------------

@app.get("/api/jobs/{job_id}/clips/{clip_id}")
def preview_clip(job_id: str, clip_id: int):
    file_path = find_completed_clip(job_id, clip_id)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        content_disposition_type="inline"
    )


# --------------------------------------------------
# Download a generated Short
# --------------------------------------------------

@app.get("/api/jobs/{job_id}/clips/{clip_id}/download")
def download_clip(job_id: str, clip_id: int):
    file_path = find_completed_clip(job_id, clip_id)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=file_path.name,
        content_disposition_type="attachment"
    )
