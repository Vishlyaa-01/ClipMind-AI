
import json
import time
from pathlib import Path

from app.services.highlight_service_backup import (
    detect_highlights
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent

TRANSCRIPT_DIR = (
    BASE_DIR / "storage" / "temp" / "transcripts"
)


def format_timestamp(seconds: float) -> str:
    """
    Convert seconds into HH:MM:SS.mmm format.
    """

    total_ms = round(seconds * 1000)

    hours, remainder = divmod(
        total_ms, 3600000
    )

    minutes, remainder = divmod(
        remainder, 60000
    )

    secs, milliseconds = divmod(
        remainder, 1000
    )

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{milliseconds:03d}"
    )


def validate_highlights(highlights: list) -> None:
    """
    Verify clip durations and check
    that selected highlights do not overlap.
    """

    for clip in highlights:

        start = clip["start"]
        end = clip["end"]

        duration = end - start

        if not 19.99 <= duration <= 30.01:

            raise ValueError(
                f"Invalid clip duration: "
                f"{duration:.2f} seconds"
            )

    # Check chronological overlap
    ordered = sorted(
        highlights,
        key=lambda clip: clip["start"]
    )

    for index in range(1, len(ordered)):

        previous = ordered[index - 1]
        current = ordered[index]

        if current["start"] < previous["end"]:

            raise ValueError(
                "Overlapping highlights detected."
            )


def main():

    print("=" * 60)
    print("CLIPMIND AI - HIGHLIGHT DETECTION TEST")
    print("=" * 60)

    # Find complete transcript files
    # Ignore the short sample transcript
    transcript_files = [
        file
        for file in TRANSCRIPT_DIR.glob("*.json")
        if not file.stem.endswith("_sample")
    ]

    if not transcript_files:

        print("\nNo full transcripts found.")
        print(
            "Run test_full_transcription.py first."
        )

        return

    # Select the latest complete transcript
    transcript_path = max(
        transcript_files,
        key=lambda file: file.stat().st_mtime
    )

    print("\nSelected transcript:")
    print(transcript_path)

    try:

        # Read transcript information
        with open(
            transcript_path,
            "r",
            encoding="utf-8"
        ) as file:

            transcript = json.load(file)

        duration = transcript.get(
            "duration_seconds", 0
        )

        segments = transcript.get(
            "segments", []
        )

        print(
            f"\nVideo audio duration: "
            f"{duration / 60:.2f} minutes"
        )

        print(
            f"Speech segments: "
            f"{len(segments)}"
        )

        print(
            f"Language: "
            f"{transcript.get('language')}"
        )

        print("\nHighlight settings:")
        print("Number of clips: 5")
        print("Minimum duration: 20 seconds")
        print("Maximum duration: 30 seconds")
        print("Scoring method: Heuristic V1")

        print(
            "\nStarting automatic "
            "highlight detection..."
        )

        start_time = time.perf_counter()

        # Detect highlights
        result = detect_highlights(
            transcript_path=str(
                transcript_path
            ),
            clip_count=5,
            min_duration=20,
            max_duration=30
        )

        elapsed_time = (
            time.perf_counter() - start_time
        )

        highlights = result["highlights"]

        # Validate selected clips
        validate_highlights(highlights)

        # Print final results
        print("\n" + "=" * 60)
        print("HIGHLIGHT DETECTION RESULTS")
        print("=" * 60)

        print(
            f"\nTotal candidate clips: "
            f"{result['total_candidates']}"
        )

        print(
            f"Selected highlights: "
            f"{result['selected_clips']}"
        )

        print(
            f"Processing time: "
            f"{elapsed_time:.2f} seconds"
        )

        # Display each selected highlight
        for clip in highlights:

            print("\n" + "-" * 60)

            print(
                f"HIGHLIGHT #{clip['clip_id']}"
            )

            print("-" * 60)

            print(
                f"Title: {clip['title']}"
            )

            print(
                f"Start: "
                f"{format_timestamp(clip['start'])}"
            )

            print(
                f"End: "
                f"{format_timestamp(clip['end'])}"
            )

            print(
                f"Duration: "
                f"{clip['duration']:.2f} seconds"
            )

            print(
                f"Highlight score: "
                f"{clip['score']}/100"
            )

            print("\nScore breakdown:")

            details = clip["score_details"]

            print(
                f"  Opening hook: "
                f"{details['hook_score']}/25"
            )

            print(
                f"  Emotional language: "
                f"{details['emotion_score']}/25"
            )

            print(
                f"  Curiosity: "
                f"{details['curiosity_score']}/20"
            )

            print(
                f"  Speech density: "
                f"{details['speech_score']}/20"
            )

            print(
                f"  Sentence structure: "
                f"{details['structure_score']}/10"
            )

            print("\nRecognized dialogue:")

            print(clip["text"])

        # Print validation results
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)

        print("Clip duration check: PASSED")
        print("Overlap check: PASSED")

        if len(highlights) == 5:

            print("Requested clip count: PASSED")

        else:

            print(
                "Requested clip count: "
                f"Only {len(highlights)} "
                "suitable clips found."
            )

        print("\nHighlights JSON saved to:")

        print(result["highlights_path"])

        print(
            "\nClipMind AI highlight detection "
            "test completed successfully!"
        )

    except Exception as error:

        print("\nHighlight detection failed:")

        print(error)


if __name__ == "__main__":
    main()
