
import json
import math
import subprocess
import time
from pathlib import Path

from app.services.video_service import (
    get_video_metadata
)


# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent

OUTPUT_DIR = (
    BASE_DIR / "storage" / "output"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def create_clip(
    video_path: str,
    start_time: float,
    end_time: float,
    output_path: str
) -> dict:
    """
    Extract a video clip using FFmpeg.

    Output:
    MP4 video
    H.264 video codec
    AAC audio codec
    Original aspect ratio
    """

    video_path = Path(video_path)

    output_path = Path(output_path)

    if not video_path.is_file():

        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    start_time = float(start_time)
    end_time = float(end_time)

    if not math.isfinite(start_time):

        raise ValueError(
            "Invalid start time."
        )

    if not math.isfinite(end_time):

        raise ValueError(
            "Invalid end time."
        )

    if start_time < 0:

        raise ValueError(
            "Start time cannot be negative."
        )

    if end_time <= start_time:

        raise ValueError(
            "End time must be greater "
            "than start time."
        )

    duration = end_time - start_time

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Use a temporary output file.
    # This prevents incomplete clips from
    # being mistaken for finished videos.

    temp_path = output_path.with_name(
        f"{output_path.stem}.partial.mp4"
    )

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel", "error",

        "-y",

        # Seek to the selected start time
        "-ss", f"{start_time:.3f}",

        # Original video
        "-i", str(video_path),

        # Selected clip duration
        "-t", f"{duration:.3f}",

        # Select first video stream
        "-map", "0:v:0",

        # Select first audio stream if available
        "-map", "0:a:0?",

        # Ensure even dimensions for H.264
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",

        # Video encoding
        "-c:v", "libx264",

        "-preset", "fast",

        "-crf", "23",

        "-pix_fmt", "yuv420p",

        # Audio encoding
        "-c:a", "aac",

        "-b:a", "128k",

        # Limit CPU threads
        "-threads", "4",

        # Improve browser playback
        "-movflags", "+faststart",

        # Temporary output
        str(temp_path)
    ]

    try:

        start_processing = time.perf_counter()

        subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=600
        )

        if not temp_path.is_file():

            raise RuntimeError(
                "FFmpeg did not create a clip."
            )

        if temp_path.stat().st_size == 0:

            raise RuntimeError(
                "Generated clip is empty."
            )

        # Analyze generated clip
        metadata = get_video_metadata(
            str(temp_path)
        )

        if not metadata.get("video_codec"):

            raise RuntimeError(
                "Generated file contains "
                "no video stream."
            )

        actual_duration = metadata[
            "duration_seconds"
        ]

        # Allow a small difference caused
        # by frame and audio boundaries
        if abs(actual_duration - duration) > 0.5:

            raise RuntimeError(
                f"Unexpected clip duration. "
                f"Expected {duration:.2f}s, "
                f"got {actual_duration:.2f}s."
            )

        # Rename only after successful validation
        temp_path.replace(output_path)

        elapsed_time = (
            time.perf_counter()
            - start_processing
        )

        return {
            "status": "success",
            "filename": output_path.name,
            "file_path": str(output_path),
            "start": round(start_time, 2),
            "end": round(end_time, 2),
            "requested_duration": round(
                duration, 2
            ),
            "actual_duration": actual_duration,
            "resolution": metadata["resolution"],
            "video_codec": metadata["video_codec"],
            "audio_codec": metadata["audio_codec"],
            "has_audio": metadata["has_audio"],
            "size_mb": metadata["size_mb"],
            "processing_time_seconds": round(
                elapsed_time, 2
            )
        }

    except subprocess.CalledProcessError as error:

        raise RuntimeError(
            f"FFmpeg clip generation failed: "
            f"{error.stderr}"
        ) from error

    except subprocess.TimeoutExpired as error:

        raise RuntimeError(
            "Clip generation timed out."
        ) from error

    finally:

        # Remove incomplete temporary files
        if temp_path.exists():

            temp_path.unlink()


def generate_clips(
    video_path: str,
    highlights_path: str
) -> dict:
    """
    Generate multiple MP4 clips from
    a highlights JSON file.
    """

    video_path = Path(video_path)

    highlights_path = Path(highlights_path)

    if not video_path.is_file():

        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    if not highlights_path.is_file():

        raise FileNotFoundError(
            f"Highlights file not found: "
            f"{highlights_path}"
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
            "No highlights found."
        )

    # Verify that the highlights belong
    # to the selected source video

    expected_transcript = (
        f"{video_path.stem}.json"
    )

    source_transcript = highlight_data.get(
        "source_transcript"
    )

    if source_transcript != expected_transcript:

        raise ValueError(
            "Highlights do not match the "
            "selected source video."
        )

    # Analyze original video
    video_metadata = get_video_metadata(
        str(video_path)
    )

    if not video_metadata.get("video_codec"):

        raise ValueError(
            "Source file contains no video."
        )

    video_duration = video_metadata[
        "duration_seconds"
    ]

    # Create a separate output folder
    # for each source video

    video_output_dir = (
        OUTPUT_DIR / video_path.stem
    )

    video_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\nPreparing video clips...")

    print(
        f"Source video: {video_path.name}"
    )

    print(
        f"Video duration: "
        f"{video_duration:.2f} seconds"
    )

    print(
        f"Original resolution: "
        f"{video_metadata['resolution']}"
    )

    print(
        f"Highlights to generate: "
        f"{len(highlights)}"
    )

    generated_clips = []

    failed_clips = []

    total_start_time = time.perf_counter()

    # Generate clips one at a time
    for index, highlight in enumerate(
        highlights,
        start=1
    ):

        print("\n" + "-" * 50)

        print(
            f"Generating clip "
            f"{index}/{len(highlights)}"
        )

        try:

            start_time = float(
                highlight["start"]
            )

            end_time = float(
                highlight["end"]
            )

            if end_time > video_duration + 0.05:

                raise ValueError(
                    "Highlight exceeds the "
                    "source video duration."
                )

            end_time = min(
                end_time,
                video_duration
            )

            print(
                f"Start: {start_time:.2f}s"
            )

            print(
                f"End: {end_time:.2f}s"
            )

            print(
                f"Duration: "
                f"{end_time - start_time:.2f}s"
            )

            output_filename = (
                f"highlight_{index:02d}.mp4"
            )

            output_path = (
                video_output_dir
                / output_filename
            )

            # Generate actual video clip
            clip_result = create_clip(
                video_path=str(video_path),
                start_time=start_time,
                end_time=end_time,
                output_path=str(output_path)
            )

            # Preserve highlight information
            clip_result["clip_id"] = highlight.get(
                "clip_id",
                index
            )

            clip_result["title"] = highlight.get(
                "title",
                f"Highlight {index}"
            )

            clip_result["score"] = highlight.get(
                "score",
                0
            )

            clip_result["text"] = highlight.get(
                "text",
                ""
            )

            generated_clips.append(
                clip_result
            )

            print(
                f"Clip created: "
                f"{output_filename}"
            )

            print(
                f"File size: "
                f"{clip_result['size_mb']} MB"
            )

            print(
                f"Processing time: "
                f"{clip_result['processing_time_seconds']}"
                f" seconds"
            )

        except Exception as error:

            failed_clips.append({
                "clip_id": highlight.get(
                    "clip_id",
                    index
                ),
                "error": str(error)
            })

            print(
                f"Clip generation failed: "
                f"{error}"
            )

    total_elapsed_time = (
        time.perf_counter()
        - total_start_time
    )

    # Determine final job status
    if not generated_clips:

        status = "failed"

    elif failed_clips:

        status = "partial_success"

    else:

        status = "success"

    total_size_mb = round(
        sum(
            clip["size_mb"]
            for clip in generated_clips
        ),
        2
    )

    # Prepare complete generation report
    result = {
        "status": status,
        "source_video": video_path.name,
        "source_highlights": highlights_path.name,
        "requested_clips": len(highlights),
        "generated_clips": len(generated_clips),
        "failed_clips": len(failed_clips),
        "total_size_mb": total_size_mb,
        "processing_time_seconds": round(
            total_elapsed_time,
            2
        ),
        "output_directory": str(
            video_output_dir
        ),
        "clips": generated_clips,
        "errors": failed_clips
    }

    # Save the clip generation report
    report_path = (
        video_output_dir
        / "clips_report.json"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    result["report_path"] = str(
        report_path
    )

    print("\n" + "=" * 50)

    print("CLIP GENERATION COMPLETE")

    print("=" * 50)

    print(
        f"Status: {status}"
    )

    print(
        f"Successful clips: "
        f"{len(generated_clips)}"
    )

    print(
        f"Failed clips: "
        f"{len(failed_clips)}"
    )

    print(
        f"Total size: "
        f"{total_size_mb} MB"
    )

    print(
        f"Total processing time: "
        f"{total_elapsed_time:.2f} seconds"
    )

    print(
        f"\nOutput folder: "
        f"{video_output_dir}"
    )

    return result
