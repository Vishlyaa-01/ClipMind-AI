
import json
import math
import time
from pathlib import Path
from typing import Callable, Optional

from app.services.video_service import get_video_metadata

from app.services.audio_service import extract_audio

from app.services.transcription_service import transcribe_audio

from app.services.highlight_service import detect_highlights

from app.services.clip_service import generate_clips

from app.services.vertical_service import (
    convert_clips_to_vertical,
    SUPPORTED_MODES
)

from app.services.caption_service import (
    generate_captioned_clips,
    SUPPORTED_STYLES
)


# --------------------------------------------------
# Project directories
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

OUTPUT_DIR = BASE_DIR / "storage" / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Default pipeline settings
# --------------------------------------------------

DEFAULT_CLIP_COUNT = 5

DEFAULT_MIN_DURATION = 20

DEFAULT_MAX_DURATION = 30

DEFAULT_VERTICAL_MODE = "blur_background"

DEFAULT_CAPTION_STYLE = "word_highlight"

DEFAULT_ENABLE_CAPTIONS = False

DEFAULT_WIDTH = 720

DEFAULT_HEIGHT = 1280


# --------------------------------------------------
# Progress callback type
# --------------------------------------------------

ProgressCallback = Callable[[dict], None]


# --------------------------------------------------
# Pipeline stage error
# --------------------------------------------------

class PipelineError(RuntimeError):
    """
    Error raised when a pipeline stage fails.
    """

    def __init__(self, stage: str, message: str):

        self.stage = stage

        self.message = message

        super().__init__(
            f"Pipeline failed during {stage}: {message}"
        )


# --------------------------------------------------
# Progress reporting
# --------------------------------------------------

def update_progress(
    callback: Optional[ProgressCallback],
    stage: str,
    progress: int,
    message: str,
    status: str = "processing"
) -> None:
    """
    Report the current processing stage.

    Later, FastAPI will use these updates
    to display progress in the dashboard.
    """

    progress_data = {
        "status": status,
        "stage": stage,
        "progress": max(0, min(100, progress)),
        "message": message
    }

    print("\n" + "-" * 60)

    print(f"Progress: {progress_data['progress']}%")

    print(f"Stage: {stage}")

    print(message)

    print("-" * 60)

    if callback is not None:

        callback(progress_data)


# --------------------------------------------------
# Settings validation
# --------------------------------------------------

def validate_pipeline_settings(
    clip_count: int,
    min_duration: float,
    max_duration: float,
    vertical_mode: str,
    caption_style: str,
    width: int,
    height: int
) -> None:
    """
    Validate all settings before starting
    expensive video processing.
    """

    if (
        not isinstance(clip_count, int)
        or isinstance(clip_count, bool)
        or not 1 <= clip_count <= 20
    ):

        raise ValueError(
            "Clip count must be between 1 and 20."
        )

    if not all(
        math.isfinite(value)
        for value in (
            min_duration,
            max_duration
        )
    ):

        raise ValueError(
            "Clip durations must be finite numbers."
        )

    if min_duration < 5:

        raise ValueError(
            "Minimum clip duration must be "
            "at least 5 seconds."
        )

    if max_duration > 120:

        raise ValueError(
            "Maximum clip duration cannot "
            "exceed 120 seconds."
        )

    if max_duration < min_duration:

        raise ValueError(
            "Maximum duration must be greater "
            "than or equal to minimum duration."
        )

    if vertical_mode not in SUPPORTED_MODES:

        raise ValueError(
            f"Unsupported vertical mode: "
            f"{vertical_mode}"
        )

    if caption_style not in SUPPORTED_STYLES:

        raise ValueError(
            f"Unsupported caption style: "
            f"{caption_style}"
        )

    if (width, height) not in {
        (720, 1280),
        (1080, 1920)
    }:

        raise ValueError(
            "Supported vertical resolutions are "
            "720x1280 and 1080x1920."
        )


# --------------------------------------------------
# Stage result validation
# --------------------------------------------------

def require_success(
    result: dict,
    stage: str
) -> None:
    """
    Stop the pipeline if a processing
    service did not complete successfully.
    """

    status = result.get("status")

    if status != "success":

        errors = result.get("errors", [])

        if errors:

            error_message = "; ".join(
                str(
                    error.get(
                        "error",
                        "Unknown error"
                    )
                )
                for error in errors
            )

        else:

            error_message = (
                f"Service returned status: {status}"
            )

        raise PipelineError(
            stage,
            error_message
        )


# --------------------------------------------------
# Save pipeline report
# --------------------------------------------------

def save_pipeline_report(
    report: dict,
    report_path: Path
) -> None:
    """
    Save the processing report using a
    temporary file to avoid incomplete JSON.
    """

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_path = report_path.with_suffix(
        ".json.tmp"
    )

    try:

        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                indent=4,
                ensure_ascii=False
            )

        temp_path.replace(report_path)

    finally:

        if temp_path.exists():

            temp_path.unlink()


# --------------------------------------------------
# Master processing pipeline
# --------------------------------------------------

def process_video(
    video_path: str,
    clip_count: int = DEFAULT_CLIP_COUNT,
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
    vertical_mode: str = DEFAULT_VERTICAL_MODE,
    caption_style: str = DEFAULT_CAPTION_STYLE,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    progress_callback: Optional[
        ProgressCallback
    ] = None,
    enable_captions: bool = DEFAULT_ENABLE_CAPTIONS
) -> dict:
    """
    Execute the complete ClipMind AI pipeline.

    Processing stages:

    1. Analyze source video
    2. Extract audio
    3. Transcribe speech
    4. Detect highlights
    5. Generate landscape clips
    6. Convert clips to vertical
    7. Generate synchronized captions

    Returns a complete processing report
    containing the final captioned videos.
    """

    video_path = Path(video_path).resolve()

    if not video_path.is_file():

        raise FileNotFoundError(
            f"Source video not found: {video_path}"
        )

    # Validate settings before processing

    validate_pipeline_settings(
        clip_count=clip_count,
        min_duration=min_duration,
        max_duration=max_duration,
        vertical_mode=vertical_mode,
        caption_style=caption_style,
        width=width,
        height=height
    )

    # Create source-specific output folder

    video_output_dir = (
        OUTPUT_DIR / video_path.stem
    )

    video_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    pipeline_report_path = (
        video_output_dir
        / "pipeline_report.json"
    )

    total_start_time = time.perf_counter()

    stage_timings = {}

    stage_results = {}

    current_stage = "initializing"

    current_progress = 0

    settings = {
        "clip_count": clip_count,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "vertical_mode": vertical_mode,
        "caption_style": caption_style,
        "enable_captions": enable_captions,
        "width": width,
        "height": height,
        "aspect_ratio": "9:16"
    }
    print("\n" + "=" * 60)

    print("CLIPMIND AI - MASTER PIPELINE")

    print("=" * 60)

    print(f"\nSource video: {video_path.name}")

    print(f"Requested clips: {clip_count}")

    print(
        f"Clip duration: "
        f"{min_duration}-{max_duration} seconds"
    )

    print(f"Vertical mode: {vertical_mode}")

    print(f"Caption style: {caption_style}")

    print(f"Resolution: {width}x{height}")

    try:

        # ==========================================
        # STAGE 1: VIDEO ANALYSIS
        # ==========================================

        current_stage = "video_analysis"

        current_progress = 2

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message="Analyzing source video..."
        )

        stage_start = time.perf_counter()

        metadata = get_video_metadata(
            str(video_path)
        )

        if not metadata.get("video_codec"):

            raise ValueError(
                "Source file contains no video stream."
            )

        if not metadata.get("has_audio"):

            raise ValueError(
                "Source video contains no audio. "
                "Speech-based clipping requires audio."
            )

        if (
            metadata["duration_seconds"]
            < min_duration
        ):

            raise ValueError(
                "Source video is shorter than "
                "the requested minimum clip duration."
            )

        stage_results[current_stage] = metadata

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        print(
            f"Video duration: "
            f"{metadata['duration_minutes']} minutes"
        )

        print(
            f"Original resolution: "
            f"{metadata['resolution']}"
        )

        # ==========================================
        # STAGE 2: AUDIO EXTRACTION
        # ==========================================

        current_stage = "audio_extraction"

        current_progress = 5

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message="Extracting audio from video..."
        )

        stage_start = time.perf_counter()

        audio_result = extract_audio(
            str(video_path)
        )

        require_success(
            audio_result,
            current_stage
        )

        stage_results[current_stage] = audio_result

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        # ==========================================
        # STAGE 3: AI TRANSCRIPTION
        # ==========================================

        current_stage = "transcription"

        current_progress = 10

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message=(
                "Transcribing speech using local AI. "
                "This may take several minutes..."
            )
        )

        stage_start = time.perf_counter()

        transcription_result = transcribe_audio(
            audio_result["audio_path"]
        )

        require_success(
            transcription_result,
            current_stage
        )

        stage_results[current_stage] = (
            transcription_result
        )

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        # ==========================================
        # STAGE 4: HIGHLIGHT DETECTION
        # ==========================================

        current_stage = "highlight_detection"

        current_progress = 65

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message=(
                "Analyzing transcript and "
                "selecting interesting moments..."
            )
        )

        stage_start = time.perf_counter()

        highlights_result = detect_highlights(
            transcript_path=transcription_result[
                "transcript_path"
            ],
            clip_count=clip_count,
            min_duration=min_duration,
            max_duration=max_duration
        )

        require_success(
            highlights_result,
            current_stage
        )

        if not highlights_result.get("highlights"):

            raise ValueError(
                "No suitable highlights were found."
            )

        selected_count = highlights_result[
            "selected_clips"
        ]

        stage_results[current_stage] = (
            highlights_result
        )

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        # ==========================================
        # STAGE 5: LANDSCAPE CLIP GENERATION
        # ==========================================

        current_stage = "clip_generation"

        current_progress = 68

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message=(
                f"Generating {selected_count} "
                "video highlights..."
            )
        )

        stage_start = time.perf_counter()

        clips_result = generate_clips(
            video_path=str(video_path),
            highlights_path=highlights_result[
                "highlights_path"
            ]
        )

        stage_results[current_stage] = clips_result

        require_success(
            clips_result,
            current_stage
        )

        if (
            clips_result["generated_clips"]
            != selected_count
        ):

            raise ValueError(
                "Generated clip count does not "
                "match selected highlight count."
            )

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        # ==========================================
        # STAGE 6: VERTICAL CONVERSION
        # ==========================================

        current_stage = "vertical_conversion"

        current_progress = 80

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message=(
                "Converting clips to vertical "
                "9:16 format..."
            )
        )

        stage_start = time.perf_counter()

        vertical_result = convert_clips_to_vertical(
            clips_report_path=clips_result[
                "report_path"
            ],
            mode=vertical_mode,
            width=width,
            height=height
        )

        stage_results[current_stage] = (
            vertical_result
        )

        require_success(
            vertical_result,
            current_stage
        )

        if (
            vertical_result["converted_clips"]
            != selected_count
        ):

            raise ValueError(
                "Vertical clip count does not "
                "match selected highlight count."
            )

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )
        final_video_result = vertical_result

        # ==========================================
        # STAGE 7: OPTIONAL CAPTION GENERATION
        # ==========================================

        if enable_captions:

            current_stage = "caption_generation"
            current_progress = 90

            update_progress(
                callback=progress_callback,
                stage=current_stage,
                progress=current_progress,
                message="Generating synchronized captions..."
            )

            stage_start = time.perf_counter()

            caption_result = generate_captioned_clips(
                vertical_report_path=vertical_result["report_path"],
                style=caption_style
            )

            stage_results[current_stage] = caption_result

            require_success(
                caption_result,
                current_stage
            )

            if caption_result["captioned_clips"] != selected_count:
                raise ValueError(
                    "Final captioned clip count does not "
                    "match selected highlight count."
                )

            stage_timings[current_stage] = round(
                time.perf_counter() - stage_start,
                2
            )

            final_video_result = caption_result

        else:

            current_stage = "caption_generation"
            current_progress = 90

            update_progress(
                callback=progress_callback,
                stage=current_stage,
                progress=current_progress,
                message="Captions disabled. Using clean vertical Shorts."
            )

            stage_results[current_stage] = {
                "status": "skipped",
                "reason": "Captions disabled by user setting"
            }

            stage_timings[current_stage] = 0.0        
        # ==========================================
        # STAGE 8: FINAL VALIDATION
        # ==========================================

        current_stage = "final_validation"

        current_progress = 98

        update_progress(
            callback=progress_callback,
            stage=current_stage,
            progress=current_progress,
            message="Validating final video files..."
        )

        stage_start = time.perf_counter()

        final_clips = []

        for clip in final_video_result["clips"]:

            final_video_path = Path(
                clip["file_path"]
            )

            srt_path = (
                Path(clip["srt_path"])
                if enable_captions
                else None
            )

            ass_path = (
                Path(clip["ass_path"])
                if enable_captions
                else None
            )

            # Verify the MP4 always exists.
            # Subtitle files are required only when captions are enabled.

            required_files = [final_video_path]

            if enable_captions:
                required_files.extend([srt_path, ass_path])

            for output_path in required_files:

                if not output_path.is_file():

                    raise FileNotFoundError(
                        f"Final output missing: {output_path}"
                    )

                if output_path.stat().st_size == 0:

                    raise ValueError(
                        f"Final output is empty: {output_path}"
                    )
            # Verify final video metadata

            final_metadata = get_video_metadata(
                str(final_video_path)
            )

            if (
                final_metadata["width"] != width
                or final_metadata["height"] != height
            ):

                raise ValueError(
                    f"Incorrect final resolution: "
                    f"{final_video_path.name}"
                )

            if (
                final_metadata["video_codec"]
                != "h264"
            ):

                raise ValueError(
                    f"Incorrect final video codec: "
                    f"{final_video_path.name}"
                )

            if (
                not final_metadata["has_audio"]
                or final_metadata["audio_codec"]
                != "aac"
            ):

                raise ValueError(
                    f"Incorrect final audio: "
                    f"{final_video_path.name}"
                )

            expected_duration = (
                float(clip["end"])
                - float(clip["start"])
            )

            if abs(
                final_metadata["duration_seconds"]
                - expected_duration
            ) > 0.5:

                raise ValueError(
                    f"Final clip duration mismatch: "
                    f"{final_video_path.name}"
                )

            # Store information needed by
            # the future dashboard

            final_clips.append({
                "clip_id": clip["clip_id"],
                "title": clip["title"],
                "score": clip["score"],
                "text": clip.get("text", ""),
                "filename": clip["filename"],
                "file_path": str(final_video_path),
                "start": clip["start"],
                "end": clip["end"],
                "duration_seconds": (
                    final_metadata["duration_seconds"]
                ),
                "resolution": (
                    final_metadata["resolution"]
                ),
                "aspect_ratio": "9:16",
                "video_codec": (
                    final_metadata["video_codec"]
                ),
                "audio_codec": (
                    final_metadata["audio_codec"]
                ),
                "has_audio": (
                    final_metadata["has_audio"]
                ),
                "size_mb": (
                    final_metadata["size_mb"]
                ),
                "caption_style": caption_style if enable_captions else "none",
                "enable_captions": enable_captions,
                "vertical_mode": vertical_mode,
                "total_words": clip.get("total_words", 0) if enable_captions else 0,
                "caption_groups": clip.get("caption_groups", 0) if enable_captions else 0,
                "srt_path": str(srt_path) if srt_path is not None else None,
                "ass_path": str(ass_path) if ass_path is not None else None
            })

        stage_timings[current_stage] = round(
            time.perf_counter() - stage_start,
            2
        )

        # ==========================================
        # BUILD FINAL PIPELINE REPORT
        # ==========================================

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        total_output_size = round(
            sum(
                clip["size_mb"]
                for clip in final_clips
            ),
            2
        )

        total_clip_duration = round(
            sum(
                clip["duration_seconds"]
                for clip in final_clips
            ),
            2
        )

        warnings = []

        if len(final_clips) < clip_count:

            warnings.append(
                f"Requested {clip_count} clips, "
                f"but only {len(final_clips)} "
                "suitable non-overlapping "
                "highlights were available."
            )

        report = {
            "status": "success",
            "stage": "completed",
            "progress": 100,
            "source_video": video_path.name,
            "source_video_path": str(video_path),
            "source_metadata": metadata,
            "settings": settings,
            "requested_clips": clip_count,
            "selected_clips": selected_count,
            "generated_clips": len(final_clips),
            "total_output_size_mb": total_output_size,
            "total_clip_duration_seconds": (
                total_clip_duration
            ),
            "processing_time_seconds": round(
                total_elapsed_time,
                2
            ),
            "stage_timings": stage_timings,
            "stage_results": stage_results,
            "output_directory": (
                final_video_result["output_directory"]
            ),
            "clips": final_clips,
            "warnings": warnings,
            "report_path": str(
                pipeline_report_path
            )
        }

        save_pipeline_report(
            report,
            pipeline_report_path
        )

        # ==========================================
        # PIPELINE COMPLETE
        # ==========================================

        update_progress(
            callback=progress_callback,
            stage="completed",
            progress=100,
            message=(
                f"Successfully generated "
                f"{len(final_clips)} captioned Shorts!"
            ),
            status="success"
        )

        print("\n" + "=" * 60)

        print("CLIPMIND AI - PIPELINE COMPLETE")

        print("=" * 60)

        print("\nStatus: success")

        print(
            f"Requested clips: "
            f"{clip_count}"
        )

        print(
            f"Generated clips: "
            f"{len(final_clips)}"
        )

        print(
            f"Total output size: "
            f"{total_output_size} MB"
        )

        print(
            f"Total processing time: "
            f"{total_elapsed_time:.2f} seconds"
        )

        print("\nSTAGE PROCESSING TIMES")

        for stage_name, elapsed in (
            stage_timings.items()
        ):

            print(
                f"{stage_name}: "
                f"{elapsed:.2f}s"
            )

        if warnings:

            print("\nWARNINGS")

            for warning in warnings:

                print(warning)

        print("\nFinal output folder:")

        print(
            final_video_result["output_directory"]
        )

        print("\nPipeline report:")

        print(pipeline_report_path)

        return report

    except Exception as error:

        # Save useful error information so
        # the dashboard can display it later.

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        if isinstance(error, PipelineError):

            error_message = error.message

        else:

            error_message = str(error)

        failure_report = {
            "status": "failed",
            "stage": current_stage,
            "progress": current_progress,
            "source_video": video_path.name,
            "source_video_path": str(video_path),
            "settings": settings,
            "error": error_message,
            "processing_time_seconds": round(
                total_elapsed_time,
                2
            ),
            "stage_timings": stage_timings,
            "stage_results": stage_results,
            "report_path": str(
                pipeline_report_path
            )
        }

        try:

            save_pipeline_report(
                failure_report,
                pipeline_report_path
            )

        except Exception as report_error:

            print(
                f"Could not save failure report: "
                f"{report_error}"
            )

        try:

            update_progress(
                callback=progress_callback,
                stage=current_stage,
                progress=current_progress,
                message=error_message,
                status="failed"
            )

        except Exception as callback_error:

            print(
                f"Could not report failure progress: "
                f"{callback_error}"
            )

        print("\n" + "=" * 60)

        print("CLIPMIND AI - PIPELINE FAILED")

        print("=" * 60)

        print(
            f"Failed stage: {current_stage}"
        )

        print(
            f"Error: {error_message}"
        )

        if isinstance(error, PipelineError):

            raise

        raise PipelineError(
            current_stage,
            error_message
        ) from error
