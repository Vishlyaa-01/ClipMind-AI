
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp


BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_VIDEO_SIZE = 500 * 1024 * 1024


def validate_youtube_url(url: str) -> str:
    """
    Validate a single YouTube video or Shorts URL.
    Return a clean canonical YouTube URL.
    """
    if not isinstance(url, str):
        raise ValueError("A YouTube URL is required.")

    url = url.strip()

    if not url or len(url) > 2048:
        raise ValueError("Invalid YouTube URL.")

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("YouTube URL must use HTTPS.")

    host = (parsed.hostname or "").lower()

    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid YouTube URL.")

    if parsed.username or parsed.password or port:
        raise ValueError("Invalid YouTube URL.")

    video_id = None

    if host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com"
    }:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        else:
            match = re.fullmatch(
                r"/(?:shorts|live)/([A-Za-z0-9_-]{11})/?",
                parsed.path
            )
            if match:
                video_id = match.group(1)

    elif host == "youtu.be":
        match = re.fullmatch(
            r"/([A-Za-z0-9_-]{11})/?",
            parsed.path
        )
        if match:
            video_id = match.group(1)

    if not video_id or not re.fullmatch(
        r"[A-Za-z0-9_-]{11}",
        video_id
    ):
        raise ValueError(
            "Please enter a valid YouTube video or Shorts link."
        )

    return f"https://www.youtube.com/watch?v={video_id}"


def check_available_space(directory: Path, minimum_bytes: int):
    """
    Ensure the destination drive has enough free space.
    """
    free_bytes = shutil.disk_usage(directory).free

    if free_bytes < minimum_bytes:
        raise ValueError(
            "Not enough free disk space for YouTube import."
        )


def download_youtube_video(url: str) -> dict:
    """
    Download a YouTube video into ClipMind AI storage.

    Uses metadata checks and download progress hooks
    to reduce the risk of oversized downloads.
    """
    clean_url = validate_youtube_url(url)

    video_id = clean_url.split("v=", 1)[1]
    saved_stem = uuid.uuid4().hex

    # Keep this import's temporary files isolated.
    temp_dir = UPLOAD_DIR / f"_youtube_{saved_stem}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    output_template = str(
        temp_dir / (saved_stem + ".%(ext)s")
    )

    # Allow room for separate video/audio streams and
    # FFmpeg merging, plus a safety margin.
    check_available_space(
        UPLOAD_DIR,
        MAX_VIDEO_SIZE * 3
    )

    def download_progress_hook(progress):
        if progress.get("status") != "downloading":
            return

        downloaded = progress.get("downloaded_bytes") or 0
        total = (
            progress.get("total_bytes") or
            progress.get("total_bytes_estimate")
        )

        if total and total > MAX_VIDEO_SIZE:
            raise ValueError(
                "YouTube video exceeds the 500 MB limit."
            )

        if downloaded > MAX_VIDEO_SIZE:
            raise ValueError(
                "YouTube download exceeded the 500 MB limit."
            )

        # Also check disk space during downloading.
        if shutil.disk_usage(UPLOAD_DIR).free < MAX_VIDEO_SIZE:
            raise ValueError(
                "Insufficient disk space during YouTube import."
            )

    options = {
        "format": (
            "bestvideo[ext=mp4][height<=720]+"
            "bestaudio[ext=m4a]/"
            "best[ext=mp4][height<=720]/"
            "best[height<=720]"
        ),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "max_filesize": MAX_VIDEO_SIZE,
        "overwrites": False,
        "progress_hooks": [download_progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            # Inspect metadata without downloading.
            info = downloader.extract_info(
                clean_url,
                download=False
            )

            if not info:
                raise RuntimeError(
                    "Could not retrieve YouTube video information."
                )

            if info.get("is_live"):
                raise ValueError(
                    "Live YouTube streams are not supported."
                )

            # Estimate selected stream sizes before download.
            selected_formats = info.get("requested_formats")

            if selected_formats:
                formats_to_check = selected_formats
            else:
                formats_to_check = [info]

            known_total = 0

            for video_format in formats_to_check:
                size = (
                    video_format.get("filesize") or
                    video_format.get("filesize_approx")
                )

                if size:
                    known_total += int(size)

            if known_total > MAX_VIDEO_SIZE:
                raise ValueError(
                    "Selected YouTube video is larger than 500 MB."
                )

            # Download using the selected format.
            info = downloader.extract_info(
                clean_url,
                download=True
            )

        candidates = [
            path for path in temp_dir.iterdir()
            if path.is_file() and
            path.suffix.lower() in {
                ".mp4", ".mkv", ".webm", ".mov"
            }
        ]

        if len(candidates) != 1:
            raise RuntimeError(
                "YouTube import did not produce one video file."
            )

        video_path = candidates[0]
        file_size = video_path.stat().st_size

        if file_size == 0 or file_size > MAX_VIDEO_SIZE:
            raise ValueError(
                "Downloaded video is empty or exceeds 500 MB."
            )

        final_path = UPLOAD_DIR / video_path.name

        # Move the completed video to the uploads folder.
        video_path.replace(final_path)

        return {
            "status": "success",
            "message": "YouTube video imported successfully.",
            "source": "youtube",
            "youtube_id": video_id,
            "title": info.get("title") or "YouTube Video",
            "duration_seconds": info.get("duration"),
            "saved_filename": final_path.name,
            "file_path": str(final_path),
            "size_mb": round(
                final_path.stat().st_size / (1024 * 1024),
                2
            ),
        }

    finally:
        # Remove all incomplete or intermediate files.
        shutil.rmtree(temp_dir, ignore_errors=True)
