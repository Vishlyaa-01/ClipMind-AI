
import json
import time
from pathlib import Path

from app.services.vertical_service import (
    convert_to_vertical,
    convert_clips_to_vertical
)

from app.services.video_service import (
    get_video_metadata
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "storage" / "output"

# Default vertical resolution
WIDTH = 720
HEIGHT = 1280


def find_latest_clips_report() -> Path:
    """
    Find the most recent successful
    landscape clip generation report.
    """

    reports = list(
        OUTPUT_DIR.glob("*/clips_report.json")
    )

    if not reports:

        raise FileNotFoundError(
            "No clips_report.json files found. "
            "Run test_clips.py first."
        )

    # Check newest reports first
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
        "No successful clip generation "
        "reports found."
    )


def print_clip_result(result: dict) -> None:
    """
    Display information about
    a converted vertical clip.
    """

    print("\n" + "-" * 60)

    print(
        f"Filename: {result['filename']}"
    )

    print(
        f"Mode: {result['mode']}"
    )

    print(
        f"Source resolution: "
        f"{result['source_resolution']}"
    )

    print(
        f"Output resolution: "
        f"{result['resolution']}"
    )

    print(
        f"Aspect ratio: "
        f"{result['aspect_ratio']}"
    )

    print(
        f"Duration: "
        f"{result['duration_seconds']}s"
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

    print(
        f"Saved to: "
        f"{result['file_path']}"
    )


def validate_vertical_clip(
    result: dict,
    source_metadata: dict
) -> None:
    """
    Verify resolution, duration,
    video codec and audio preservation.
    """

    output_path = Path(
        result["file_path"]
    )

    if not output_path.is_file():

        raise FileNotFoundError(
            f"Output file not found: "
            f"{output_path}"
        )

    metadata = get_video_metadata(
        str(output_path)
    )

    if (
        metadata["width"] != WIDTH
        or metadata["height"] != HEIGHT
    ):

        raise ValueError(
            "Output resolution is incorrect."
        )

    if (
        metadata["width"] * 16
        != metadata["height"] * 9
    ):

        raise ValueError(
            "Output aspect ratio is not 9:16."
        )

    if metadata["video_codec"] != "h264":

        raise ValueError(
            "Output video codec is incorrect."
        )

    if source_metadata["has_audio"]:

        if not metadata["has_audio"]:

            raise ValueError(
                "Output audio is missing."
            )

        if metadata["audio_codec"] != "aac":

            raise ValueError(
                "Output audio codec is incorrect."
            )

    duration_difference = abs(
        metadata["duration_seconds"]
        - source_metadata["duration_seconds"]
    )

    if duration_difference > 0.5:

        raise ValueError(
            "Output duration changed "
            "unexpectedly."
        )


def test_both_modes(
    clips_report_path: Path,
    clips_report: dict
) -> None:
    """
    Convert the first clip into both
    vertical framing modes.
    """

    first_clip = clips_report["clips"][0]

    input_path = (
        clips_report_path.parent
        / Path(first_clip["filename"]).name
    )

    if not input_path.is_file():

        raise FileNotFoundError(
            f"Source clip not found: "
            f"{input_path}"
        )

    source_metadata = get_video_metadata(
        str(input_path)
    )

    comparison_dir = (
        clips_report_path.parent
        / "vertical_comparison"
    )

    comparison_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n" + "=" * 60)
    print("VERTICAL MODE COMPARISON")
    print("=" * 60)

    print(
        f"\nSource clip: {input_path.name}"
    )

    print(
        f"Source resolution: "
        f"{source_metadata['resolution']}"
    )

    print(
        f"Duration: "
        f"{source_metadata['duration_seconds']}s"
    )

    print(
        f"Target resolution: "
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        "\nWe will create two versions "
        "of the same clip."
    )

    confirmation = input(
        "\nStart comparison test? (y/n): "
    ).strip().lower()

    if confirmation != "y":

        print("\nComparison test cancelled.")

        return

    start_time = time.perf_counter()

    # Version 1: Center Crop
    print("\nGenerating Center Crop version...")

    crop_output = (
        comparison_dir
        / f"{input_path.stem}_center_crop.mp4"
    )

    crop_result = convert_to_vertical(
        input_path=str(input_path),
        output_path=str(crop_output),
        mode="center_crop",
        width=WIDTH,
        height=HEIGHT
    )

    validate_vertical_clip(
        crop_result,
        source_metadata
    )

    # Version 2: Blurred Background
    print(
        "\nGenerating Blurred Background "
        "version..."
    )

    blur_output = (
        comparison_dir
        / f"{input_path.stem}_blur_background.mp4"
    )

    blur_result = convert_to_vertical(
        input_path=str(input_path),
        output_path=str(blur_output),
        mode="blur_background",
        width=WIDTH,
        height=HEIGHT
    )

    validate_vertical_clip(
        blur_result,
        source_metadata
    )

    elapsed_time = (
        time.perf_counter() - start_time
    )

    print("\n" + "=" * 60)
    print("VERTICAL COMPARISON RESULTS")
    print("=" * 60)

    print_clip_result(crop_result)

    print_clip_result(blur_result)

    # Save comparison report
    comparison_report = {
        "status": "success",
        "source_clip": input_path.name,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "aspect_ratio": "9:16",
        "processing_time_seconds": round(
            elapsed_time, 2
        ),
        "clips": [
            crop_result,
            blur_result
        ]
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

    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    print("Center Crop conversion: PASSED")
    print("Blurred Background conversion: PASSED")
    print("Vertical resolution check: PASSED")
    print("Aspect ratio check: PASSED")
    print("Duration accuracy check: PASSED")
    print("Video and audio codec check: PASSED")

    print(
        f"\nTotal comparison time: "
        f"{elapsed_time:.2f} seconds"
    )

    print("\nComparison output folder:")

    print(comparison_dir)

    print("\nComparison report:")

    print(report_path)

    print(
        "\nVertical comparison test "
        "completed successfully!"
    )

    print(
        "\nOpen both MP4 files and compare "
        "their framing and playback quality."
    )


def test_all_clips(
    clips_report_path: Path,
    clips_report: dict,
    mode: str
) -> None:
    """
    Convert all existing landscape clips
    using the selected vertical mode.
    """

    print("\n" + "=" * 60)
    print("BATCH VERTICAL CONVERSION")
    print("=" * 60)

    print(
        f"\nMode: {mode}"
    )

    print(
        f"Resolution: {WIDTH}x{HEIGHT}"
    )

    print(
        f"Clips to convert: "
        f"{len(clips_report['clips'])}"
    )

    confirmation = input(
        "\nConvert all clips? (y/n): "
    ).strip().lower()

    if confirmation != "y":

        print("\nBatch conversion cancelled.")

        return

    result = convert_clips_to_vertical(
        clips_report_path=str(
            clips_report_path
        ),
        mode=mode,
        width=WIDTH,
        height=HEIGHT
    )

    print("\n" + "=" * 60)
    print("FINAL VERTICAL CONVERSION RESULTS")
    print("=" * 60)

    print(
        f"\nStatus: {result['status']}"
    )

    print(
        f"Mode: {result['mode']}"
    )

    print(
        f"Requested clips: "
        f"{result['requested_clips']}"
    )

    print(
        f"Converted clips: "
        f"{result['converted_clips']}"
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

    # Match each converted clip with
    # its original landscape clip.
    source_clips = {
        clip["filename"]: clip
        for clip in clips_report["clips"]
    }

    for clip in result["clips"]:

        source_clip = source_clips[
            clip["source_filename"]
        ]

        source_path = (
            clips_report_path.parent
            / Path(source_clip["filename"]).name
        )

        source_metadata = get_video_metadata(
            str(source_path)
        )

        validate_vertical_clip(
            clip,
            source_metadata
        )

        print_clip_result(clip)

    if result["errors"]:

        print("\nCONVERSION ERRORS")

        for error in result["errors"]:

            print(
                f"Clip {error['clip_id']}: "
                f"{error['error']}"
            )

    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    if (
        result["status"] == "success"
        and result["converted_clips"]
        == result["requested_clips"]
        and result["failed_clips"] == 0
    ):

        print("Output files check: PASSED")
        print("Vertical resolution check: PASSED")
        print("Aspect ratio check: PASSED")
        print("Duration accuracy check: PASSED")
        print("Video and audio codec check: PASSED")
        print("Requested clip count: PASSED")

        print(
            "\nClipMind AI batch vertical "
            "conversion completed successfully!"
        )

    else:

        print(
            "Batch conversion validation: FAILED"
        )

        print(
            "Review the conversion errors above."
        )

    print("\nOutput folder:")

    print(result["output_directory"])

    print("\nVertical conversion report:")

    print(result["report_path"])


def main():

    print("=" * 60)
    print("CLIPMIND AI - VERTICAL VIDEO TEST")
    print("=" * 60)

    try:

        clips_report_path = (
            find_latest_clips_report()
        )

        print("\nSelected clips report:")

        print(clips_report_path)

        with open(
            clips_report_path,
            "r",
            encoding="utf-8"
        ) as file:

            clips_report = json.load(file)

        print(
            f"\nSource video: "
            f"{clips_report.get('source_video')}"
        )

        print(
            f"Available landscape clips: "
            f"{len(clips_report['clips'])}"
        )

        print("\nSELECT TEST MODE")

        print(
            "1. Compare Center Crop and "
            "Blurred Background"
        )

        print(
            "2. Convert all clips using "
            "Blurred Background"
        )

        print(
            "3. Convert all clips using "
            "Center Crop"
        )

        print("4. Exit")

        choice = input(
            "\nEnter your choice (1-4): "
        ).strip()

        if choice == "1":

            test_both_modes(
                clips_report_path,
                clips_report
            )

        elif choice == "2":

            test_all_clips(
                clips_report_path,
                clips_report,
                mode="blur_background"
            )

        elif choice == "3":

            test_all_clips(
                clips_report_path,
                clips_report,
                mode="center_crop"
            )

        elif choice == "4":

            print("\nTest cancelled.")

        else:

            print(
                "\nInvalid choice. "
                "Please run the test again."
            )

    except Exception as error:

        print("\nVertical video test failed:")

        print(error)


if __name__ == "__main__":
    main()
