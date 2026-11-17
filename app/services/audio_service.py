
import subprocess
from pathlib import Path


# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIO_DIR = BASE_DIR / "storage" / "temp" / "audio"

# Create audio directory automatically
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def extract_audio(video_path: str) -> dict:
    """
    Extract audio from a video using FFmpeg.

    Output format:
    WAV, 16 kHz, mono, 16-bit PCM
    """

    video_path = Path(video_path)

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Video file not found: {video_path}"
        )

    # Generate output audio filename
    audio_filename = f"{video_path.stem}.wav"
    audio_path = AUDIO_DIR / audio_filename

    # FFmpeg audio extraction command
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-map", "0:a:0",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path)
    ]

    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=600
        )

        if not audio_path.is_file():
            raise RuntimeError(
                "Audio extraction failed."
            )

        return {
            "status": "success",
            "audio_filename": audio_filename,
            "audio_path": str(audio_path),
            "format": "wav",
            "sample_rate": 16000,
            "channels": 1,
            "size_mb": round(
                audio_path.stat().st_size / (1024 * 1024),
                2
            )
        }

    except subprocess.CalledProcessError as error:

        if audio_path.exists():
            audio_path.unlink()

        raise RuntimeError(
            f"FFmpeg audio extraction failed: {error.stderr}"
        ) from error

    except Exception:

        if audio_path.exists():
            audio_path.unlink()

        raise
