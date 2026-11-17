
import json
import time
from pathlib import Path

from app.services.clip_service import (
    generate_clips
)

from app.services.video_service import (
    get_video_metadata
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = (
    BASE_DIR / "storage" / "uploads"
)

HIGHLIGHT_DIR = (
    BASE_DIR / "storage" / "temp" / "highlights"
)

ALLOWED_FORMATS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm"
}


def find_matching_video(highlights_path: Path):
    """
    Find the original video that belongs
    to the selected highlights JSON.
    """

    with open(
        highlights_path,
        "r",
        encoding="utf-8"
    ) as file:

        highlight_data = json.load(file)

    source_transcript = highlight_data.get(
        "source_transcript"
    )

    if not source_transcript:

        raise ValueError(
            "Highlights file does not identify "
            "its source transcript."
        )

    # The video and transcript use the same
    # unique filename, with different extensions.
    source_stem = Path(
        source_transcript
    ).stem

    matching_videos = [
        file
        for file in UPLOAD_DIR.iterdir()
        if file.is_file()
        and file.stem == source_stem
        and file.suffix.lower() in ALLOWED_FORMATS
    ]

    if not matching_videos:

        raise FileNotFoundError(
            f"No original video found for "
            f"transcript: {source_transcript}"
        )

    if len(matching_videos) > 1:

        raise ValueError(
            "Multiple matching videos found. "
            "Cannot safely select the source."
        )

    return matching_videos[0]


def format_timestamp(seconds: float) -> str:
    """
    Convert seconds into HH:MM:SS.mmm.
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


def main():

    print("=" * 60)
    print("CLIPMIND AI - VIDEO CLIP GENERATION TEST")
    print("=" * 60)

    try:

        # Verify required folders
        if not UPLOAD_DIR.is_dir():

            raise FileNotFoundError(
                "Video uploads folder not found."
            )

        if not HIGHLIGHT_DIR.is_dir():

            raise FileNotFoundError(
                "Highlights folder not found. "
                "Run test_highlights.py first."
            )

        # Find generated highlights files
        highlight_files = list(
            HIGHLIGHT_DIR.glob(
                "*_highlights.json"
            )
        )

        if not highlight_files:

            raise FileNotFoundError(
                "No highlights JSON files found. "
                "Run test_highlights.py first."
            )

        # Select the latest highlights file
        highlights_path = max(
            highlight_files,
            key=lambda file: file.stat().st_mtime
        )

        print("\nSelected highlights file:")

        print(highlights_path)

        # Find the exact matching original video
        video_path = find_matching_video(
            highlights_path
        )

        print("\nMatching source video:")

        print(video_path)

        # Read source video information
        metadata = get_video_metadata(
            str(video_path)
        )

        print("\nSOURCE VIDEO INFORMATION")

        print(
            f"Duration: "
            f"{metadata['duration_minutes']} minutes"
        )

        print(
            f"Resolution: "
            f"{metadata['resolution']}"
        )

        print(
            f"Video codec: "
            f"{metadata['video_codec']}"
        )

        print(
            f"Audio codec: "
            f"{metadata['audio_codec']}"
        )

        print(
            f"File size: "
            f"{metadata['size_mb']} MB"
        )

        # Read highlight instructions
        with open(
            highlights_path,
            "r",
            encoding="utf-8"
        ) as file:

            highlight_data = json.load(file)

        highlights = highlight_data.get(
            "highlights",
            []
        )

        if not highlights:

            raise ValueError(
                "Highlights file contains no clips."
            )

        print("\nCLIPS TO GENERATE")

        for index, clip in enumerate(
            highlights,
            start=1
        ):

            print(
                f"\nClip {index}: "
                f"{clip.get('title', 'Highlight')}"
            )

            print(
                f"  Start: "
                f"{format_timestamp(clip['start'])}"
            )

            print(
                f"  End: "
                f"{format_timestamp(clip['end'])}"
            )

            print(
                f"  Duration: "
                f"{clip['duration']:.2f}s"
            )

            print(
                f"  Score: "
                f"{clip['score']}/100"
            )

        print("\nOUTPUT SETTINGS")

        print("Format: MP4")
        print("Video codec: H.264")
        print("Audio codec: AAC")
        print("Aspect ratio: Original")
        print("Encoding preset: Fast")
        print("Quality: CRF 23")

        print(
            "\nThe clips will be generated "
            "one at a time."
        )

        print(
            "Please keep this terminal open "
            "until processing finishes."
        )

        # Ask before starting video rendering
        confirmation = input(
            "\nGenerate video clips? (y/n): "
        ).strip().lower()

        if confirmation != "y":

            print("\nClip generation cancelled.")

            return

        # Start rendering
        start_time = time.perf_counter()

        result = generate_clips(
            video_path=str(video_path),
            highlights_path=str(highlights_path)
        )

        total_time = (
            time.perf_counter() - start_time
        )

        print("\n" + "=" * 60)

        print("FINAL CLIP GENERATION RESULTS")

        print("=" * 60)

        print(
            f"\nStatus: "
            f"{result['status']}"
        )

        print(
            f"Requested clips: "
            f"{result['requested_clips']}"
        )

        print(
            f"Generated clips: "
            f"{result['generated_clips']}"
        )

        print(
            f"Failed clips: "
            f"{result['failed_clips']}"
        )

        print(
            f"Total output size: "
            f"{result['total_size_mb']} MB"
        )

        print(
            f"Total test time: "
            f"{total_time:.2f} seconds"
        )

        # Print information about each output
        for clip in result["clips"]:

            print("\n" + "-" * 60)

            print(
                f"CLIP #{clip['clip_id']}"
            )

            print("-" * 60)

            print(
                f"Filename: "
                f"{clip['filename']}"
            )

            print(
                f"Title: "
                f"{clip['title']}"
            )

            print(
                f"Highlight score: "
                f"{clip['score']}/100"
            )

            print(
                f"Requested duration: "
                f"{clip['requested_duration']}s"
            )

            print(
                f"Actual duration: "
                f"{clip['actual_duration']}s"
            )

            print(
                f"Resolution: "
                f"{clip['resolution']}"
            )

            print(
                f"Video codec: "
                f"{clip['video_codec']}"
            )

            print(
                f"Audio codec: "
                f"{clip['audio_codec']}"
            )

            print(
                f"Has audio: "
                f"{clip['has_audio']}"
            )

            print(
                f"File size: "
                f"{clip['size_mb']} MB"
            )

            print(
                f"Processing time: "
                f"{clip['processing_time_seconds']}s"
            )

            print(
                f"Saved to: "
                f"{clip['file_path']}"
            )

        # Display errors if any clips failed
        if result["errors"]:

            print("\nCLIP GENERATION ERRORS")

            for error in result["errors"]:

                print(
                    f"Clip {error['clip_id']}: "
                    f"{error['error']}"
                )

        # Final validation
        print("\n" + "=" * 60)

        print("VALIDATION RESULTS")

        print("=" * 60)

        all_files_exist = all(
            Path(clip["file_path"]).is_file()
            for clip in result["clips"]
        )

        all_durations_valid = all(
            abs(
                clip["actual_duration"]
                - clip["requested_duration"]
            ) <= 0.5
            for clip in result["clips"]
        )

        all_codecs_valid = all(
            clip["video_codec"] == "h264"
            and (
                not metadata["has_audio"]
                or (
                    clip["has_audio"]
                    and clip["audio_codec"] == "aac"
                )
            )
            for clip in result["clips"]
        )

        all_clips_generated = (
            result["generated_clips"]
            == result["requested_clips"]
            and result["failed_clips"] == 0
        )

        print(
            "Output files check: "
            + (
                "PASSED"
                if result["clips"] and all_files_exist
                else "FAILED"
            )
        )

        print(
            "Duration accuracy check: "
            + (
                "PASSED"
                if result["clips"] and all_durations_valid
                else "FAILED"
            )
        )

        print(
            "Video and audio codec check: "
            + (
                "PASSED"
                if result["clips"] and all_codecs_valid
                else "FAILED"
            )
        )

        print(
            "Requested clip count: "
            + (
                "PASSED"
                if all_clips_generated
                else "FAILED"
            )
        )

        print("\nOutput folder:")

        print(result["output_directory"])

        print("\nGeneration report:")

        print(result["report_path"])

        if (
            result["status"] == "success"
            and all_files_exist
            and all_durations_valid
            and all_codecs_valid
            and all_clips_generated
        ):

            print(
                "\nClipMind AI video clip "
                "generation test completed "
                "successfully!"
            )

            print(
                "\nOpen the generated MP4 files "
                "to verify video playback and "
                "audio synchronization."
            )

        else:

            print(
                "\nSome validation checks failed. "
                "Review the results above."
            )

    except Exception as error:

        print("\nVideo clip generation test failed:")

        print(error)


if __name__ == "__main__":
    main()
