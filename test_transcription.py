
import subprocess
import json
import time
from pathlib import Path

from app.services.transcription_service import (
    transcribe_audio
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent

AUDIO_DIR = (
    BASE_DIR / "storage" / "temp" / "audio"
)

SAMPLE_DIR = (
    BASE_DIR / "storage" / "temp" / "samples"
)

SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def main():

    # Find extracted audio files
    audio_files = list(AUDIO_DIR.glob("*.wav"))

    if not audio_files:
        print("No extracted audio files found.")
        print("Run test_audio.py first.")
        return

    # Select the most recently modified audio
    audio_path = max(
        audio_files,
        key=lambda file: file.stat().st_mtime
    )

    print("=" * 50)
    print("CLIPMIND AI - TRANSCRIPTION TEST")
    print("=" * 50)

    print("\nOriginal audio:")
    print(audio_path)

    # Create a short sample for testing
    sample_path = (
        SAMPLE_DIR / f"{audio_path.stem}_sample.wav"
    )

    print("\nCreating 60-second audio sample...")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", "60",
        "-i", str(audio_path),
        "-t", "60",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(sample_path)
    ]

    try:

        subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=120
        )

        if not sample_path.is_file():
            raise RuntimeError(
                "Audio sample was not created."
            )

        # A WAV file must contain audio data
        if sample_path.stat().st_size <= 100:
            raise RuntimeError(
                "Audio sample is empty. "
                "Try using a longer audio file."
            )

        print("Audio sample created successfully!")
        print(sample_path)

        print(
            "\nStarting local AI transcription..."
        )

        print(
            "The Whisper model may download "
            "automatically on the first run.\n"
        )

        start_time = time.time()

        # Run AI transcription
        result = transcribe_audio(
            str(sample_path)
        )

        total_time = time.time() - start_time

        print("\n" + "=" * 50)
        print("TRANSCRIPTION TEST RESULTS")
        print("=" * 50)

        print(json.dumps(result, indent=4))

        print(
            f"\nTotal test time: "
            f"{total_time:.2f} seconds"
        )

        print(
            "\nClipMind AI transcription test "
            "completed successfully!"
        )

    except subprocess.CalledProcessError as error:

        print("\nFFmpeg error:")
        print(error.stderr)

    except Exception as error:

        print("\nTranscription test failed:")
        print(error)


if __name__ == "__main__":
    main()
