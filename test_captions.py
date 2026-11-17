
import json
import time
from pathlib import Path

from app.services.caption_service import (
    load_transcript,
    generate_captioned_clip,
    generate_captioned_clips
)

from app.services.video_service import (
    get_video_metadata
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = (
    BASE_DIR / "storage" / "output"
)

TRANSCRIPT_DIR = (
    BASE_DIR
    / "storage"
    / "temp"
    / "transcripts"
)


# Caption styles to test
CAPTION_STYLES = [
    "word_highlight",
    "classic",
    "bold_yellow"
]


def find_latest_vertical_report() -> Path:
    """
    Find the latest successful vertical
    conversion report.
    """

    reports = list(
        OUTPUT_DIR.glob(
            "*/vertical/*/*/vertical_report.json"
        )
    )

    if not reports:

        raise FileNotFoundError(
            "No vertical_report.json files found. "
            "Run test_vertical.py first."
        )

    reports.sort(
        key=lambda file: file.stat().st_mtime,
        reverse=True
    )

    for report_path in reports:

        with open(
            report_path,
            "r",
            encoding="utf-8"
        ) as file:

            report = json.load(file)

        if (
            report.get("status") == "success"
            and report.get("clips")
        ):

            return report_path

    raise ValueError(
        "No successful vertical conversion "
        "reports found."
    )


def find_matching_transcript(
    vertical_report: dict
) -> Path:
    """
    Locate the exact Whisper transcript
    belonging to the original source video.
    """

    source_video = vertical_report.get(
        "source_video"
    )

    if not source_video:

        raise ValueError(
            "Vertical report does not identify "
            "the original source video."
        )

    source_stem = Path(
        source_video
    ).stem

    transcript_path = (
        TRANSCRIPT_DIR
        / f"{source_stem}.json"
    )

    if not transcript_path.is_file():

        raise FileNotFoundError(
            f"Matching transcript not found: "
            f"{transcript_path}"
        )

    transcript = load_transcript(
        str(transcript_path)
    )

    expected_audio = (
        f"{source_stem}.wav"
    )

    if (
        transcript.get("audio_filename")
        != expected_audio
    ):

        raise ValueError(
            "Transcript does not match "
            "the original source video."
        )

    return transcript_path


def print_caption_result(
    result: dict
) -> None:
    """
    Display information about a
    generated captioned video.
    """

    print("\n" + "-" * 60)

    print(
        f"Filename: "
        f"{result['filename']}"
    )

    print(
        f"Caption style: "
        f"{result['caption_style']}"
    )

    print(
        f"Resolution: "
        f"{result['resolution']}"
    )

    print(
        f"Duration: "
        f"{result['duration_seconds']}s"
    )

    print(
        f"Total caption words: "
        f"{result['total_words']}"
    )

    print(
        f"Caption groups: "
        f"{result['caption_groups']}"
    )

    print(
        f"Video codec: "
        f"{result['video_codec']}"
    )

    print(
        f"Audio codec: "
        f"{result['audio_codec']}"
    )

    print(
        f"Has audio: "
        f"{result['has_audio']}"
    )

    print(
        f"File size: "
        f"{result['size_mb']} MB"
    )

    print(
        f"Processing time: "
        f"{result['processing_time_seconds']}s"
    )

    print("\nCaptioned video:")

    print(result["file_path"])

    print("\nSRT subtitle file:")

    print(result["srt_path"])

    print("\nASS subtitle file:")

    print(result["ass_path"])


def validate_caption_result(
    result: dict,
    source_metadata: dict
) -> None:
    """
    Validate the generated video
    and subtitle files.
    """

    video_path = Path(
        result["file_path"]
    )

    srt_path = Path(
        result["srt_path"]
    )

    ass_path = Path(
        result["ass_path"]
    )

    # Check all required files
    for file_path in (
        video_path,
        srt_path,
        ass_path
    ):

        if not file_path.is_file():

            raise FileNotFoundError(
                f"Output file not found: "
                f"{file_path}"
            )

        if file_path.stat().st_size == 0:

            raise ValueError(
                f"Output file is empty: "
                f"{file_path}"
            )

    # Read output video metadata
    metadata = get_video_metadata(
        str(video_path)
    )

    # Validate output resolution
    if (
        metadata["width"]
        != source_metadata["width"]
        or metadata["height"]
        != source_metadata["height"]
    ):

        raise ValueError(
            "Video resolution changed "
            "during caption rendering."
        )

    # Validate vertical aspect ratio
    if (
        metadata["width"] * 16
        != metadata["height"] * 9
    ):

        raise ValueError(
            "Output aspect ratio is not 9:16."
        )

    # Validate duration
    duration_difference = abs(
        metadata["duration_seconds"]
        - source_metadata["duration_seconds"]
    )

    if duration_difference > 0.5:

        raise ValueError(
            "Video duration changed "
            "unexpectedly."
        )

    # Validate video codec
    if metadata["video_codec"] != "h264":

        raise ValueError(
            "Output video codec is incorrect."
        )

    # Validate audio
    if (
        metadata["has_audio"]
        != source_metadata["has_audio"]
    ):

        raise ValueError(
            "Audio availability changed "
            "during caption rendering."
        )

    if (
        source_metadata["has_audio"]
        and metadata["audio_codec"]
        != source_metadata["audio_codec"]
    ):

        raise ValueError(
            "Audio codec changed unexpectedly."
        )

    # Validate caption counts
    if result["total_words"] < 1:

        raise ValueError(
            "No caption words were generated."
        )

    if result["caption_groups"] < 1:

        raise ValueError(
            "No caption groups were generated."
        )

    # Basic SRT content validation
    srt_text = srt_path.read_text(
        encoding="utf-8-sig"
    )

    if "-->" not in srt_text:

        raise ValueError(
            "SRT file contains no subtitle timings."
        )

    # Basic ASS content validation
    ass_text = ass_path.read_text(
        encoding="utf-8-sig"
    )

    if "[Events]" not in ass_text:

        raise ValueError(
            "ASS subtitle events section is missing."
        )

    if "Dialogue:" not in ass_text:

        raise ValueError(
            "ASS file contains no dialogue events."
        )

    # Check active-word color formatting
    if (
        result["caption_style"]
        == "word_highlight"
    ):

        if r"{\1c&H0000FFFF&}" not in ass_text:

            raise ValueError(
                "Active-word highlighting "
                "was not generated."
            )


def print_validation_results():
    """
    Print the successful validation checks.
    """

    print("\n" + "=" * 60)

    print("VALIDATION RESULTS")

    print("=" * 60)

    print("Output MP4 file check: PASSED")

    print("SRT subtitle file check: PASSED")

    print("ASS subtitle file check: PASSED")

    print("Vertical resolution check: PASSED")

    print("Aspect ratio check: PASSED")

    print("Duration accuracy check: PASSED")

    print("Video and audio codec check: PASSED")

    print("Caption content check: PASSED")


def test_caption_styles(
    vertical_report_path: Path,
    vertical_report: dict,
    transcript_path: Path
) -> None:
    """
    Generate three caption styles
    using the first vertical clip.
    """

    first_clip = vertical_report["clips"][0]

    input_path = (
        vertical_report_path.parent
        / Path(first_clip["filename"]).name
    )

    if not input_path.is_file():

        raise FileNotFoundError(
            f"Vertical clip not found: "
            f"{input_path}"
        )

    source_metadata = get_video_metadata(
        str(input_path)
    )

    transcript = load_transcript(
        str(transcript_path)
    )

    comparison_dir = (
        vertical_report_path.parent
        / "caption_comparison"
    )

    comparison_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n" + "=" * 60)

    print("CAPTION STYLE COMPARISON")

    print("=" * 60)

    print(
        f"\nSource clip: "
        f"{input_path.name}"
    )

    print(
        f"Resolution: "
        f"{source_metadata['resolution']}"
    )

    print(
        f"Duration: "
        f"{source_metadata['duration_seconds']}s"
    )

    print(
        f"Original start: "
        f"{first_clip['start']}s"
    )

    print(
        f"Original end: "
        f"{first_clip['end']}s"
    )

    print(
        f"Transcript: "
        f"{transcript_path.name}"
    )

    print("\nStyles to generate:")

    print("1. Word Highlight")

    print("2. Classic")

    print("3. Bold Yellow")

    confirmation = input(
        "\nStart caption comparison? (y/n): "
    ).strip().lower()

    if confirmation != "y":

        print("\nComparison test cancelled.")

        return

    results = []

    start_time = time.perf_counter()

    for index, style in enumerate(
        CAPTION_STYLES,
        start=1
    ):

        print("\n" + "=" * 50)

        print(
            f"Generating style "
            f"{index}/{len(CAPTION_STYLES)}"
        )

        print(
            f"Style: {style}"
        )

        style_output_dir = (
            comparison_dir / style
        )

        result = generate_captioned_clip(
            input_path=str(input_path),
            transcript=transcript,
            clip_start=first_clip["start"],
            clip_end=first_clip["end"],
            output_dir=str(style_output_dir),
            style=style
        )

        # Preserve highlight information
        result["clip_id"] = first_clip.get(
            "clip_id",
            1
        )

        result["title"] = first_clip.get(
            "title",
            "Highlight 1"
        )

        result["score"] = first_clip.get(
            "score",
            0
        )

        # Validate the generated files
        validate_caption_result(
            result,
            source_metadata
        )

        results.append(result)

    elapsed_time = (
        time.perf_counter() - start_time
    )

    print("\n" + "=" * 60)

    print("CAPTION COMPARISON RESULTS")

    print("=" * 60)

    for result in results:

        print_caption_result(result)

    # Save comparison report
    comparison_report = {
        "status": "success",
        "source_clip": input_path.name,
        "source_transcript": str(
            transcript_path
        ),
        "styles_tested": len(results),
        "processing_time_seconds": round(
            elapsed_time,
            2
        ),
        "clips": results
    }

    report_path = (
        comparison_dir
        / "comparison_report.json"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            comparison_report,
            file,
            indent=4,
            ensure_ascii=False
        )

    print_validation_results()

    print(
        "All three caption styles: PASSED"
    )

    print(
        f"\nTotal comparison time: "
        f"{elapsed_time:.2f} seconds"
    )

    print("\nComparison output folder:")

    print(comparison_dir)

    print("\nComparison report:")

    print(report_path)

    print(
        "\nCaption comparison test "
        "completed successfully!"
    )

    print(
        "\nWatch all three captioned videos "
        "to verify caption appearance "
        "and synchronization."
    )


def test_all_captions(
    vertical_report_path: Path,
    vertical_report: dict,
    style: str
) -> None:
    """
    Generate captions for all vertical
    clips using the selected style.
    """

    print("\n" + "=" * 60)

    print("BATCH CAPTION GENERATION")

    print("=" * 60)

    print(
        f"\nCaption style: {style}"
    )

    print(
        f"Clips to process: "
        f"{len(vertical_report['clips'])}"
    )

    confirmation = input(
        "\nCaption all clips? (y/n): "
    ).strip().lower()

    if confirmation != "y":

        print("\nBatch captioning cancelled.")

        return

    result = generate_captioned_clips(
        vertical_report_path=str(
            vertical_report_path
        ),
        style=style
    )

    print("\n" + "=" * 60)

    print("FINAL CAPTION GENERATION RESULTS")

    print("=" * 60)

    print(
        f"\nStatus: "
        f"{result['status']}"
    )

    print(
        f"Caption style: "
        f"{result['caption_style']}"
    )

    print(
        f"Requested clips: "
        f"{result['requested_clips']}"
    )

    print(
        f"Captioned clips: "
        f"{result['captioned_clips']}"
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
        f"Total processing time: "
        f"{result['processing_time_seconds']}s"
    )

    # Match each captioned clip with
    # its original vertical video
    source_clips = {
        clip["filename"]: clip
        for clip in vertical_report["clips"]
    }

    for clip in result["clips"]:

        source_clip = source_clips[
            clip["source_filename"]
        ]

        source_path = (
            vertical_report_path.parent
            / Path(source_clip["filename"]).name
        )

        source_metadata = get_video_metadata(
            str(source_path)
        )

        validate_caption_result(
            clip,
            source_metadata
        )

        print_caption_result(clip)

    if result["errors"]:

        print("\nCAPTION GENERATION ERRORS")

        for error in result["errors"]:

            print(
                f"Clip {error['clip_id']}: "
                f"{error['error']}"
            )

    if (
        result["status"] == "success"
        and result["captioned_clips"]
        == result["requested_clips"]
        and result["failed_clips"] == 0
    ):

        print_validation_results()

        print("Requested clip count: PASSED")

        print(
            "\nClipMind AI batch caption "
            "generation completed successfully!"
        )

    else:

        print(
            "\nBatch caption validation: FAILED"
        )

        print(
            "Review the caption generation "
            "errors above."
        )

    print("\nOutput folder:")

    print(result["output_directory"])

    print("\nCaption generation report:")

    print(result["report_path"])


def main():

    print("=" * 60)

    print("CLIPMIND AI - CAPTION GENERATION TEST")

    print("=" * 60)

    try:

        # Find the latest successful
        # vertical conversion report
        vertical_report_path = (
            find_latest_vertical_report()
        )

        print("\nSelected vertical report:")

        print(vertical_report_path)

        with open(
            vertical_report_path,
            "r",
            encoding="utf-8"
        ) as file:

            vertical_report = json.load(file)

        # Locate the matching transcript
        transcript_path = (
            find_matching_transcript(
                vertical_report
            )
        )

        print("\nMatching transcript:")

        print(transcript_path)

        print(
            f"\nSource video: "
            f"{vertical_report['source_video']}"
        )

        print(
            f"Vertical mode: "
            f"{vertical_report['mode']}"
        )

        print(
            f"Available vertical clips: "
            f"{len(vertical_report['clips'])}"
        )

        print("\nSELECT TEST MODE")

        print(
            "1. Compare all three caption styles"
        )

        print(
            "2. Caption all clips using "
            "Word Highlight"
        )

        print(
            "3. Caption all clips using Classic"
        )

        print(
            "4. Caption all clips using Bold Yellow"
        )

        print("5. Exit")

        choice = input(
            "\nEnter your choice (1-5): "
        ).strip()

        if choice == "1":

            test_caption_styles(
                vertical_report_path,
                vertical_report,
                transcript_path
            )

        elif choice == "2":

            test_all_captions(
                vertical_report_path,
                vertical_report,
                style="word_highlight"
            )

        elif choice == "3":

            test_all_captions(
                vertical_report_path,
                vertical_report,
                style="classic"
            )

        elif choice == "4":

            test_all_captions(
                vertical_report_path,
                vertical_report,
                style="bold_yellow"
            )

        elif choice == "5":

            print("\nTest cancelled.")

        else:

            print(
                "\nInvalid choice. "
                "Please run the test again."
            )

    except Exception as error:

        print("\nCaption generation test failed:")

        print(error)

        raise SystemExit(1)


if __name__ == "__main__":
    main()
