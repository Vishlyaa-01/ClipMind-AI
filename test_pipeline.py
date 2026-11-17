
import json
import shutil
import time
import uuid
from pathlib import Path

from app.services.pipeline_service import (
    process_video,
    PipelineError
)

from app.services.video_service import (
    get_video_metadata
)


# --------------------------------------------------
# Project directories
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = (
    BASE_DIR / "storage" / "uploads"
)

OUTPUT_DIR = (
    BASE_DIR / "storage" / "output"
)


# --------------------------------------------------
# Original successful test video
# --------------------------------------------------

SOURCE_VIDEO_NAME = (
    "b32dd3b2a1274792b8e04277bc836b41.mkv"
)


# --------------------------------------------------
# Pipeline test settings
# --------------------------------------------------

CLIP_COUNT = 5

MIN_DURATION = 20

MAX_DURATION = 30

VERTICAL_MODE = "blur_background"

CAPTION_STYLE = "word_highlight"

WIDTH = 720

HEIGHT = 1280


# --------------------------------------------------
# Progress tracking
# --------------------------------------------------

progress_history = []


def handle_progress(update: dict) -> None:
    """
    Receive progress updates from the
    master processing pipeline.
    """

    progress_history.append(
        update.copy()
    )

    progress = update["progress"]

    bar_length = 30

    filled_length = round(
        bar_length * progress / 100
    )

    progress_bar = (
        "#" * filled_length
        + "-" * (
            bar_length - filled_length
        )
    )

    print(
        f"\n[{progress_bar}] "
        f"{progress}%"
    )

    print(
        f"Pipeline status: "
        f"{update['status']}"
    )

    print(
        f"Current stage: "
        f"{update['stage']}"
    )

    print(
        f"Message: "
        f"{update['message']}"
    )


# --------------------------------------------------
# Find original source video
# --------------------------------------------------

def find_source_video() -> Path:
    """
    Use the previously verified video
    for a reproducible pipeline test.
    """

    source_path = (
        UPLOAD_DIR / SOURCE_VIDEO_NAME
    )

    if not source_path.is_file():

        raise FileNotFoundError(
            f"Original test video not found: "
            f"{source_path}"
        )

    return source_path


# --------------------------------------------------
# Create isolated test copy
# --------------------------------------------------

def create_test_video_copy(
    source_path: Path
) -> Path:
    """
    Create a uniquely named copy so
    existing successful outputs are
    not overwritten.
    """

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    unique_name = (
        f"{uuid.uuid4().hex}"
        f"{source_path.suffix.lower()}"
    )

    test_path = (
        UPLOAD_DIR / unique_name
    )

    source_size = (
        source_path.stat().st_size
    )

    free_space = shutil.disk_usage(
        UPLOAD_DIR
    ).free

    # Basic storage safety check:
    # source copy plus 1 GB working space.

    required_space = (
        source_size
        + 1024 * 1024 * 1024
    )

    if free_space < required_space:

        raise RuntimeError(
            "Not enough free disk space "
            "for the pipeline test."
        )

    print("\nCreating isolated test copy...")

    print(
        f"Original: {source_path.name}"
    )

    print(
        f"Test copy: {test_path.name}"
    )

    start_time = time.perf_counter()

    try:

        shutil.copy2(
            source_path,
            test_path
        )

        if (
            test_path.stat().st_size
            != source_size
        ):

            raise RuntimeError(
                "Test video copy is incomplete."
            )

    except Exception:

        if test_path.exists():

            test_path.unlink()

        raise

    elapsed_time = (
        time.perf_counter() - start_time
    )

    print(
        f"Test copy created in "
        f"{elapsed_time:.2f} seconds."
    )

    print(
        f"Test video path: {test_path}"
    )

    return test_path


# --------------------------------------------------
# Validate final pipeline report
# --------------------------------------------------

def validate_pipeline_result(
    result: dict,
    test_video_path: Path
) -> None:
    """
    Validate the complete pipeline result
    and all final captioned videos.
    """

    if result.get("status") != "success":

        raise ValueError(
            "Pipeline did not finish successfully."
        )

    if result.get("progress") != 100:

        raise ValueError(
            "Pipeline progress did not reach 100%."
        )

    if (
        result.get("source_video")
        != test_video_path.name
    ):

        raise ValueError(
            "Pipeline report references "
            "the wrong source video."
        )

    if (
        result["requested_clips"]
        != CLIP_COUNT
    ):

        raise ValueError(
            "Requested clip count is incorrect."
        )

    clips = result.get("clips", [])

    if not clips:

        raise ValueError(
            "No final clips were generated."
        )

    if (
        len(clips)
        != result["generated_clips"]
    ):

        raise ValueError(
            "Final clip count does not "
            "match the pipeline report."
        )

    if (
        result["generated_clips"]
        != result["selected_clips"]
    ):

        raise ValueError(
            "Generated clip count does not "
            "match selected highlights."
        )

    if len(clips) != CLIP_COUNT:

        raise ValueError(
            f"Expected {CLIP_COUNT} clips "
            f"for this test, but received "
            f"{len(clips)}."
        )

    # Verify the expected output directory.

    expected_output_dir = (
        OUTPUT_DIR
        / test_video_path.stem
    ).resolve()

    # Verify the final pipeline report.

    report_path = Path(
        result["report_path"]
    ).resolve()

    if not report_path.is_file():

        raise FileNotFoundError(
            "Pipeline report was not created."
        )

    if (
        report_path.parent
        != expected_output_dir
    ):

        raise ValueError(
            "Pipeline report is outside "
            "the expected output folder."
        )

    with open(
        report_path,
        "r",
        encoding="utf-8"
    ) as file:

        saved_report = json.load(file)

    if (
        saved_report.get("status")
        != "success"
    ):

        raise ValueError(
            "Saved pipeline report is invalid."
        )

    if (
        saved_report.get("generated_clips")
        != len(clips)
    ):

        raise ValueError(
            "Saved report clip count is incorrect."
        )

    # Validate each final video.

    clip_ranges = []

    clip_ids = set()

    for clip in clips:

        clip_id = clip["clip_id"]

        if clip_id in clip_ids:

            raise ValueError(
                "Duplicate clip ID found."
            )

        clip_ids.add(clip_id)

        video_path = Path(
            clip["file_path"]
        ).resolve()

        srt_path = Path(
            clip["srt_path"]
        ).resolve()

        ass_path = Path(
            clip["ass_path"]
        ).resolve()

        # Verify all three output files.

        for file_path in (
            video_path,
            srt_path,
            ass_path
        ):

            if not file_path.is_file():

                raise FileNotFoundError(
                    f"Output file missing: "
                    f"{file_path}"
                )

            if file_path.stat().st_size == 0:

                raise ValueError(
                    f"Output file is empty: "
                    f"{file_path}"
                )

            if not file_path.is_relative_to(
                expected_output_dir
            ):

                raise ValueError(
                    f"Unexpected output location: "
                    f"{file_path}"
                )

        # Verify final video metadata.

        metadata = get_video_metadata(
            str(video_path)
        )

        if (
            metadata["width"] != WIDTH
            or metadata["height"] != HEIGHT
        ):

            raise ValueError(
                f"Incorrect video resolution: "
                f"{video_path.name}"
            )

        if (
            metadata["width"] * 16
            != metadata["height"] * 9
        ):

            raise ValueError(
                f"Incorrect aspect ratio: "
                f"{video_path.name}"
            )

        if metadata["video_codec"] != "h264":

            raise ValueError(
                f"Incorrect video codec: "
                f"{video_path.name}"
            )

        if not metadata["has_audio"]:

            raise ValueError(
                f"Audio is missing: "
                f"{video_path.name}"
            )

        if metadata["audio_codec"] != "aac":

            raise ValueError(
                f"Incorrect audio codec: "
                f"{video_path.name}"
            )

        start = float(
            clip["start"]
        )

        end = float(
            clip["end"]
        )

        expected_duration = end - start

        actual_duration = metadata[
            "duration_seconds"
        ]

        if (
            expected_duration
            < MIN_DURATION - 0.05
            or expected_duration
            > MAX_DURATION + 0.05
        ):

            raise ValueError(
                f"Highlight duration is outside "
                f"the requested range: "
                f"{video_path.name}"
            )

        if abs(
            actual_duration
            - expected_duration
        ) > 0.5:

            raise ValueError(
                f"Final video duration mismatch: "
                f"{video_path.name}"
            )

        if (
            clip["caption_style"]
            != CAPTION_STYLE
        ):

            raise ValueError(
                "Incorrect caption style."
            )

        if (
            clip["vertical_mode"]
            != VERTICAL_MODE
        ):

            raise ValueError(
                "Incorrect vertical mode."
            )

        if clip["total_words"] < 1:

            raise ValueError(
                "No caption words found."
            )

        if clip["caption_groups"] < 1:

            raise ValueError(
                "No caption groups found."
            )

        # Verify subtitle content.

        srt_text = srt_path.read_text(
            encoding="utf-8-sig"
        )

        ass_text = ass_path.read_text(
            encoding="utf-8-sig"
        )

        if "-->" not in srt_text:

            raise ValueError(
                "SRT subtitle timings are missing."
            )

        if "Dialogue:" not in ass_text:

            raise ValueError(
                "ASS subtitle events are missing."
            )

        if CAPTION_STYLE == "word_highlight":

            if (
                r"{\1c&H0000FFFF&}"
                not in ass_text
            ):

                raise ValueError(
                    "Active-word highlighting "
                    "is missing."
                )

        clip_ranges.append(
            (start, end)
        )

    # Verify that highlights do not overlap.

    clip_ranges.sort()

    for index in range(
        1,
        len(clip_ranges)
    ):

        previous_end = (
            clip_ranges[index - 1][1]
        )

        current_start = (
            clip_ranges[index][0]
        )

        if current_start < previous_end:

            raise ValueError(
                "Selected highlights overlap."
            )

    # Verify all pipeline stages completed.

    expected_stages = [
        "video_analysis",
        "audio_extraction",
        "transcription",
        "highlight_detection",
        "clip_generation",
        "vertical_conversion",
        "caption_generation",
        "final_validation"
    ]

    stage_timings = result.get(
        "stage_timings",
        {}
    )

    for stage in expected_stages:

        if stage not in stage_timings:

            raise ValueError(
                f"Missing stage timing: {stage}"
            )

    # Verify progress callback updates.

    if not progress_history:

        raise ValueError(
            "No progress updates were received."
        )

    if (
        progress_history[-1]["progress"]
        != 100
    ):

        raise ValueError(
            "Final progress update is not 100%."
        )

    if (
        progress_history[-1]["status"]
        != "success"
    ):

        raise ValueError(
            "Final progress status is incorrect."
        )

    for index in range(
        1,
        len(progress_history)
    ):

        if (
            progress_history[index]["progress"]
            < progress_history[index - 1]["progress"]
        ):

            raise ValueError(
                "Pipeline progress moved backward."
            )


# --------------------------------------------------
# Print final test results
# --------------------------------------------------

def print_final_results(
    result: dict,
    total_test_time: float
) -> None:

    print("\n" + "=" * 60)

    print("FINAL MASTER PIPELINE TEST RESULTS")

    print("=" * 60)

    print(
        f"\nStatus: {result['status']}"
    )

    print(
        f"Source video: "
        f"{result['source_video']}"
    )

    print(
        f"Source duration: "
        f"{result['source_metadata']['duration_minutes']}"
        f" minutes"
    )

    print(
        f"Requested clips: "
        f"{result['requested_clips']}"
    )

    print(
        f"Selected highlights: "
        f"{result['selected_clips']}"
    )

    print(
        f"Generated clips: "
        f"{result['generated_clips']}"
    )

    print(
        f"Total final video duration: "
        f"{result['total_clip_duration_seconds']}s"
    )

    print(
        f"Total final video size: "
        f"{result['total_output_size_mb']} MB"
    )

    print(
        f"Pipeline processing time: "
        f"{result['processing_time_seconds']}s"
    )

    print(
        f"Total test time: "
        f"{total_test_time:.2f}s"
    )

    # Display processing performance.

    print("\n" + "=" * 60)

    print("STAGE PERFORMANCE")

    print("=" * 60)

    for stage, elapsed in (
        result["stage_timings"].items()
    ):

        print(
            f"{stage:<25} "
            f"{elapsed:>8.2f}s"
        )

    source_duration = (
        result["source_metadata"][
            "duration_seconds"
        ]
    )

    processing_time = (
        result["processing_time_seconds"]
    )

    if processing_time > 0:

        processing_speed = (
            source_duration
            / processing_time
        )

        print(
            f"\nEnd-to-end processing speed: "
            f"{processing_speed:.2f}x real time"
        )

    # Display all final clips.

    print("\n" + "=" * 60)

    print("FINAL GENERATED SHORTS")

    print("=" * 60)

    for clip in result["clips"]:

        print("\n" + "-" * 60)

        print(
            f"Clip ID: {clip['clip_id']}"
        )

        print(
            f"Title: {clip['title']}"
        )

        print(
            f"Score: {clip['score']}/100"
        )

        print(
            f"Filename: {clip['filename']}"
        )

        print(
            f"Original start: "
            f"{clip['start']}s"
        )

        print(
            f"Original end: "
            f"{clip['end']}s"
        )

        print(
            f"Duration: "
            f"{clip['duration_seconds']}s"
        )

        print(
            f"Resolution: "
            f"{clip['resolution']}"
        )

        print(
            f"Caption style: "
            f"{clip['caption_style']}"
        )

        print(
            f"Caption words: "
            f"{clip['total_words']}"
        )

        print(
            f"Caption groups: "
            f"{clip['caption_groups']}"
        )

        print(
            f"File size: "
            f"{clip['size_mb']} MB"
        )

        print(
            f"Saved to: "
            f"{clip['file_path']}"
        )

    # Display warnings, if any.

    if result.get("warnings"):

        print("\nWARNINGS")

        for warning in result["warnings"]:

            print(warning)

    # Display validation results.

    print("\n" + "=" * 60)

    print("VALIDATION RESULTS")

    print("=" * 60)

    print("Master pipeline execution: PASSED")

    print("All processing stages: PASSED")

    print("Requested clip count: PASSED")

    print("Output MP4 files: PASSED")

    print("SRT subtitle files: PASSED")

    print("ASS subtitle files: PASSED")

    print("Vertical resolution: PASSED")

    print("Aspect ratio: PASSED")

    print("Clip duration accuracy: PASSED")

    print("Non-overlapping highlights: PASSED")

    print("Video and audio codecs: PASSED")

    print("Caption content: PASSED")

    print("Progress callback: PASSED")

    print("Pipeline report: PASSED")

    print("Isolated output directory: PASSED")

    print("\nFinal output folder:")

    print(result["output_directory"])

    print("\nMaster pipeline report:")

    print(result["report_path"])

    print("\n" + "=" * 60)

    print(
        "FULL MASTER PIPELINE TEST "
        "COMPLETED SUCCESSFULLY!"
    )

    print("=" * 60)


# --------------------------------------------------
# Main test function
# --------------------------------------------------

def main():

    print("=" * 60)

    print("CLIPMIND AI - FULL PIPELINE TEST")

    print("=" * 60)

    test_video_path = None

    try:

        source_path = find_source_video()

        metadata = get_video_metadata(
            str(source_path)
        )

        print("\nOriginal source video:")

        print(source_path)

        print(
            f"\nDuration: "
            f"{metadata['duration_minutes']} minutes"
        )

        print(
            f"Resolution: "
            f"{metadata['resolution']}"
        )

        print(
            f"File size: "
            f"{metadata['size_mb']} MB"
        )

        print("\nPIPELINE SETTINGS")

        print(
            f"Clip count: {CLIP_COUNT}"
        )

        print(
            f"Clip duration: "
            f"{MIN_DURATION}-{MAX_DURATION}s"
        )

        print(
            f"Vertical mode: {VERTICAL_MODE}"
        )

        print(
            f"Caption style: {CAPTION_STYLE}"
        )

        print(
            f"Output resolution: "
            f"{WIDTH}x{HEIGHT}"
        )

        print(
            "\nThis test will create a fresh "
            "copy of the source video."
        )

        print(
            "Your existing successful clips "
            "and reports will remain unchanged."
        )

        print(
            "\nAll processing stages will "
            "run automatically."
        )

        print(
            "This may take several minutes."
        )

        confirmation = input(
            "\nStart full pipeline test? (y/n): "
        ).strip().lower()

        if confirmation != "y":

            print("\nPipeline test cancelled.")

            return

        # Start complete test timer.

        test_start_time = (
            time.perf_counter()
        )

        # Create isolated source video.

        test_video_path = (
            create_test_video_copy(
                source_path
            )
        )

        progress_history.clear()

        # Run the entire master pipeline.

        result = process_video(
            video_path=str(
                test_video_path
            ),
            clip_count=CLIP_COUNT,
            min_duration=MIN_DURATION,
            max_duration=MAX_DURATION,
            vertical_mode=VERTICAL_MODE,
            caption_style=CAPTION_STYLE,
            width=WIDTH,
            height=HEIGHT,
            progress_callback=handle_progress
        )

        # Validate all final results.

        validate_pipeline_result(
            result,
            test_video_path
        )

        total_test_time = (
            time.perf_counter()
            - test_start_time
        )

        # Save progress history for review.

        progress_report_path = (
            Path(result["report_path"]).parent
            / "progress_history.json"
        )

        with open(
            progress_report_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                progress_history,
                file,
                indent=4,
                ensure_ascii=False
            )

        # Print final benchmark.

        print_final_results(
            result,
            total_test_time
        )

        print("\nProgress history:")

        print(progress_report_path)

        print(
            "\nThe isolated test video "
            "has been retained for debugging."
        )

        print(
            "\nOpen the final output folder "
            "and watch the five generated Shorts."
        )

    except PipelineError as error:

        print("\n" + "=" * 60)

        print("MASTER PIPELINE TEST FAILED")

        print("=" * 60)

        print(
            f"\nFailed stage: {error.stage}"
        )

        print(
            f"Error: {error.message}"
        )

        if test_video_path is not None:

            failure_report_path = (
                OUTPUT_DIR
                / test_video_path.stem
                / "pipeline_report.json"
            )

            if failure_report_path.is_file():

                print("\nFailure report:")

                print(failure_report_path)

        raise SystemExit(1)

    except Exception as error:

        print("\nPipeline test failed:")

        print(error)

        raise SystemExit(1)


if __name__ == "__main__":
    main()
