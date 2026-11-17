
import subprocess
import json
from pathlib import Path


def get_video_metadata(video_path: str) -> dict:
    """
    Extract video information using FFprobe.
    """

    video_path = Path(video_path)

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Video file not found: {video_path}"
        )

    command = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(video_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=60
    )

    metadata = json.loads(result.stdout)

    video_stream = None
    audio_stream = None

    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream

        elif stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    format_info = metadata.get("format", {})

    duration = float(format_info.get("duration", 0) or 0)

    width = video_stream.get("width", 0) if video_stream else 0
    height = video_stream.get("height", 0) if video_stream else 0

    return {
        "filename": video_path.name,
        "duration_seconds": round(duration, 2),
        "duration_minutes": round(duration / 60, 2),
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}",
        "video_codec": (
            video_stream.get("codec_name")
            if video_stream else None
        ),
        "audio_codec": (
            audio_stream.get("codec_name")
            if audio_stream else None
        ),
        "has_audio": audio_stream is not None,
        "format": format_info.get("format_name"),
        "size_mb": round(
            video_path.stat().st_size / (1024 * 1024),
            2
        )
    }
