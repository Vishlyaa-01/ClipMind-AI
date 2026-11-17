
import json
import subprocess
import time
from pathlib import Path

from app.services.video_service import (
    get_video_metadata
)


# Supported vertical conversion modes
SUPPORTED_MODES = {
    "center_crop",
    "blur_background"
}


def build_vertical_filter(
    mode: str,
    width: int = 720,
    height: int = 1280
) -> str:
    """
    Build an FFmpeg video filter for
    vertical video conversion.
    """

    if mode not in SUPPORTED_MODES:

        raise ValueError(
            f"Unsupported vertical mode: {mode}"
        )

    if width <= 0 or height <= 0:

        raise ValueError(
            "Output dimensions must be positive."
        )

    if width % 2 != 0 or height % 2 != 0:

        raise ValueError(
            "Output dimensions must be even."
        )

    if width * 16 != height * 9:

        raise ValueError(
            "Output dimensions must use "
            "a 9:16 aspect ratio."
        )

    # Mode 1: Center crop
    if mode == "center_crop":

        return (
            f"[0:v:0]"
            f"scale={width}:{height}:"
            f"force_original_aspect_ratio=increase:"
            f"force_divisible_by=2,"
            f"crop={width}:{height},"
            f"setsar=1[outv]"
        )

    # Mode 2: Blurred background
    #
    # Split the original video into two layers.
    #
    # Background:
    # Scale, crop and blur to fill the screen.
    #
    # Foreground:
    # Scale the original video to fit inside
    # the vertical frame without cropping.

    return (
        f"[0:v:0]split=2[bg][fg];"

        f"[bg]"
        f"scale={width}:{height}:"
        f"force_original_aspect_ratio=increase:"
        f"force_divisible_by=2,"
        f"crop={width}:{height},"
        f"setsar=1,"
        f"gblur=sigma=20,"
        f"eq=brightness=-0.08[background];"

        f"[fg]"
        f"scale={width}:{height}:"
        f"force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2,"
        f"setsar=1[foreground];"

        f"[background][foreground]"
        f"overlay=(W-w)/2:(H-h)/2,"
        f"setsar=1[outv]"
    )


def convert_to_vertical(
    input_path: str,
    output_path: str,
    mode: str = "blur_background",
    width: int = 720,
    height: int = 1280
) -> dict:
    """
    Convert an existing video clip into
    a vertical 9:16 MP4 video.

    Supported modes:
    - center_crop
    - blur_background
    """

    input_path = Path(input_path)

    output_path = Path(output_path)

    if not input_path.is_file():

        raise FileNotFoundError(
            f"Input video not found: {input_path}"
        )

    if input_path.resolve() == output_path.resolve():

        raise ValueError(
            "Input and output files must "
            "be different."
        )

    if output_path.suffix.lower() != ".mp4":

        raise ValueError(
            "Output file must use MP4 format."
        )

    # Build vertical video filter
    video_filter = build_vertical_filter(
        mode=mode,
        width=width,
        height=height
    )

    # Read original clip metadata
    source_metadata = get_video_metadata(
        str(input_path)
    )

    if not source_metadata.get("video_codec"):

        raise ValueError(
            "Input file contains no video."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Temporary output protects against
    # incomplete video files.
    temp_path = output_path.with_name(
        f"{output_path.stem}.partial.mp4"
    )

    if temp_path.resolve() == input_path.resolve():

        raise ValueError(
            "Temporary output conflicts "
            "with the input video."
        )

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel", "error",

        "-y",

        # Input clip
        "-i", str(input_path),

        # Limit filter processing threads
        "-filter_complex_threads", "4",

        # Vertical conversion filter
        "-filter_complex", video_filter,

        # Select processed video
        "-map", "[outv]",

        # Keep original audio if available
        "-map", "0:a:0?",

        # Video encoding
        "-c:v", "libx264",

        "-preset", "fast",

        "-crf", "23",

        "-pix_fmt", "yuv420p",

        # Audio encoding
        "-c:a", "aac",

        "-b:a", "128k",

        # CPU thread limit
        "-threads", "4",

        # Browser-compatible playback
        "-movflags", "+faststart",

        # Temporary output
        str(temp_path)
    ]

    try:

        print(
            f"\nConverting: {input_path.name}"
        )

        print(
            f"Mode: {mode}"
        )

        print(
            f"Target resolution: "
            f"{width}x{height}"
        )

        start_time = time.perf_counter()

        # Run FFmpeg
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
                "Vertical video was not created."
            )

        if temp_path.stat().st_size == 0:

            raise RuntimeError(
                "Generated vertical video is empty."
            )

        # Validate output metadata
        metadata = get_video_metadata(
            str(temp_path)
        )

        if metadata["width"] != width:

            raise RuntimeError(
                "Incorrect output video width."
            )

        if metadata["height"] != height:

            raise RuntimeError(
                "Incorrect output video height."
            )

        if metadata["video_codec"] != "h264":

            raise RuntimeError(
                "Incorrect output video codec."
            )

        if source_metadata["has_audio"]:

            if not metadata["has_audio"]:

                raise RuntimeError(
                    "Audio was lost during conversion."
                )

            if metadata["audio_codec"] != "aac":

                raise RuntimeError(
                    "Incorrect output audio codec."
                )

        source_duration = source_metadata[
            "duration_seconds"
        ]

        output_duration = metadata[
            "duration_seconds"
        ]

        if abs(
            output_duration - source_duration
        ) > 0.5:

            raise RuntimeError(
                "Video duration changed "
                "unexpectedly during conversion."
            )

        # Rename only after validation
        temp_path.replace(output_path)

        elapsed_time = (
            time.perf_counter() - start_time
        )

        result = {
            "status": "success",
            "source_filename": input_path.name,
            "filename": output_path.name,
            "file_path": str(output_path),
            "mode": mode,
            "aspect_ratio": "9:16",
            "source_resolution": (
                source_metadata["resolution"]
            ),
            "resolution": metadata["resolution"],
            "width": metadata["width"],
            "height": metadata["height"],
            "duration_seconds": output_duration,
            "video_codec": metadata["video_codec"],
            "audio_codec": metadata["audio_codec"],
            "has_audio": metadata["has_audio"],
            "size_mb": metadata["size_mb"],
            "processing_time_seconds": round(
                elapsed_time, 2
            )
        }

        print(
            f"Vertical video created: "
            f"{output_path.name}"
        )

        print(
            f"Resolution: "
            f"{result['resolution']}"
        )

        print(
            f"File size: "
            f"{result['size_mb']} MB"
        )

        print(
            f"Processing time: "
            f"{result['processing_time_seconds']}s"
        )

        return result

    except subprocess.CalledProcessError as error:

        raise RuntimeError(
            f"FFmpeg vertical conversion failed: "
            f"{error.stderr}"
        ) from error

    except subprocess.TimeoutExpired as error:

        raise RuntimeError(
            "Vertical video conversion timed out."
        ) from error

    finally:

        # Remove incomplete temporary files
        if temp_path.exists():

            temp_path.unlink()


def convert_clips_to_vertical(
    clips_report_path: str,
    mode: str = "blur_background",
    width: int = 720,
    height: int = 1280
) -> dict:
    """
    Convert all successfully generated clips
    from a clips_report.json file.

    Original landscape clips are preserved.
    """

    clips_report_path = Path(
        clips_report_path
    )

    if not clips_report_path.is_file():

        raise FileNotFoundError(
            f"Clips report not found: "
            f"{clips_report_path}"
        )

    # Validate settings before processing
    build_vertical_filter(
        mode=mode,
        width=width,
        height=height
    )

    # Read original clip generation report
    with open(
        clips_report_path,
        "r",
        encoding="utf-8"
    ) as file:

        clips_report = json.load(file)

    clips = clips_report.get(
        "clips",
        []
    )

    if not clips:

        raise ValueError(
            "No generated clips found "
            "in the report."
        )

    # Keep vertical videos separate from
    # original landscape clips.
    #
    # Each mode and resolution receives
    # its own output folder.

    source_output_dir = (
        clips_report_path.parent
    )

    vertical_output_dir = (
        source_output_dir
        / "vertical"
        / mode
        / f"{width}x{height}"
    )

    vertical_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n" + "=" * 50)

    print("CLIPMIND AI - VERTICAL CONVERSION")

    print("=" * 50)

    print(
        f"\nMode: {mode}"
    )

    print(
        f"Resolution: {width}x{height}"
    )

    print(
        f"Clips to convert: {len(clips)}"
    )

    converted_clips = []

    failed_clips = []

    total_start_time = time.perf_counter()

    # Convert clips sequentially
    for index, clip in enumerate(
        clips,
        start=1
    ):

        print("\n" + "-" * 50)

        print(
            f"Converting clip "
            f"{index}/{len(clips)}"
        )

        try:

            # Locate the original landscape clip
            input_path = (
                source_output_dir
                / Path(clip["filename"]).name
            )

            output_filename = (
                f"{input_path.stem}_vertical.mp4"
            )

            output_path = (
                vertical_output_dir
                / output_filename
            )

            # Convert clip
            result = convert_to_vertical(
                input_path=str(input_path),
                output_path=str(output_path),
                mode=mode,
                width=width,
                height=height
            )

            # Preserve highlight information
            result["clip_id"] = clip.get(
                "clip_id",
                index
            )

            result["title"] = clip.get(
                "title",
                f"Highlight {index}"
            )

            result["score"] = clip.get(
                "score",
                0
            )

            result["text"] = clip.get(
                "text",
                ""
            )

            # Preserve original video timestamps.
            # These will be needed for captions.
            result["start"] = clip.get(
                "start"
            )

            result["end"] = clip.get(
                "end"
            )

            converted_clips.append(
                result
            )

        except Exception as error:

            failed_clips.append({
                "clip_id": clip.get(
                    "clip_id",
                    index
                ),
                "error": str(error)
            })

            print(
                f"Vertical conversion failed: "
                f"{error}"
            )

    total_elapsed_time = (
        time.perf_counter()
        - total_start_time
    )

    # Determine final status
    if not converted_clips:

        status = "failed"

    elif failed_clips:

        status = "partial_success"

    else:

        status = "success"

    total_size_mb = round(
        sum(
            clip["size_mb"]
            for clip in converted_clips
        ),
        2
    )

    # Create complete conversion report
    report = {
        "status": status,
        "source_video": clips_report.get(
            "source_video"
        ),
        "source_clips_report": str(
            clips_report_path
        ),
        "mode": mode,
        "aspect_ratio": "9:16",
        "resolution": f"{width}x{height}",
        "requested_clips": len(clips),
        "converted_clips": len(converted_clips),
        "failed_clips": len(failed_clips),
        "total_size_mb": total_size_mb,
        "processing_time_seconds": round(
            total_elapsed_time,
            2
        ),
        "output_directory": str(
            vertical_output_dir
        ),
        "clips": converted_clips,
        "errors": failed_clips
    }

    # Save report for later caption generation
    report_path = (
        vertical_output_dir
        / "vertical_report.json"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    report["report_path"] = str(
        report_path
    )

    print("\n" + "=" * 50)

    print("VERTICAL CONVERSION COMPLETE")

    print("=" * 50)

    print(
        f"Status: {status}"
    )

    print(
        f"Successful conversions: "
        f"{len(converted_clips)}"
    )

    print(
        f"Failed conversions: "
        f"{len(failed_clips)}"
    )

    print(
        f"Total output size: "
        f"{total_size_mb} MB"
    )

    print(
        f"Total processing time: "
        f"{total_elapsed_time:.2f} seconds"
    )

    print(
        f"\nOutput folder: "
        f"{vertical_output_dir}"
    )

    return report
