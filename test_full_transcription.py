
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


def main():

    print("=" * 60)
    print("CLIPMIND AI - FULL VIDEO TRANSCRIPTION")
    print("=" * 60)

    # Find extracted audio files
    audio_files = list(AUDIO_DIR.glob("*.wav"))

    if not audio_files:

        print("\nNo extracted audio files found.")
        print("Run test_audio.py first.")

        return

    # Select the latest extracted audio
    audio_path = max(
        audio_files,
        key=lambda file: file.stat().st_mtime
    )

    audio_size_mb = round(
        audio_path.stat().st_size / (1024 * 1024),
        2
    )

    print("\nSelected audio:")
    print(audio_path)

    print(f"\nAudio size: {audio_size_mb} MB")

    print("\nModel: Whisper Base")
    print("Device: CPU")
    print("Compute type: INT8")

    print(
        "\nThis test will transcribe the "
        "entire audio file."
    )

    print(
        "Processing may take several minutes."
    )

    print(
        "Please keep this terminal open.\n"
    )

    # Ask for confirmation
    confirmation = input(
        "Start full transcription? (y/n): "
    ).strip().lower()

    if confirmation != "y":

        print("\nTranscription cancelled.")

        return

    try:

        start_time = time.time()

        # Run full AI transcription
        result = transcribe_audio(
            str(audio_path)
        )

        total_time = time.time() - start_time

        audio_duration = result[
            "duration_seconds"
        ]

        processing_time = result[
            "processing_time_seconds"
        ]

        # Calculate transcription speed
        speed = (
            audio_duration / processing_time
            if processing_time > 0
            else 0
        )

        print("\n" + "=" * 60)
        print("FULL TRANSCRIPTION RESULTS")
        print("=" * 60)

        print(json.dumps(result, indent=4))

        print(
            f"\nAudio duration: "
            f"{audio_duration / 60:.2f} minutes"
        )

        print(
            f"AI processing time: "
            f"{processing_time / 60:.2f} minutes"
        )

        print(
            f"Total test time: "
            f"{total_time / 60:.2f} minutes"
        )

        print(
            f"Transcription speed: "
            f"{speed:.2f}x real time"
        )

        print(
            "\nFull video transcription "
            "completed successfully!"
        )

        print(
            "\nClipMind AI is ready for "
            "automatic highlight detection."
        )

    except Exception as error:

        print("\nFull transcription failed:")
        print(error)


if __name__ == "__main__":
    main()
