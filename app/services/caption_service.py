
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

TRANSCRIPT_DIR = (
    BASE_DIR
    / "storage"
    / "temp"
    / "transcripts"
)


# Supported caption styles
SUPPORTED_STYLES = {
    "word_highlight",
    "classic",
    "bold_yellow"
}


def load_transcript(
    transcript_path: str
) -> dict:
    """
    Load the existing Whisper transcript.
    """

    transcript_path = Path(transcript_path)

    if not transcript_path.is_file():

        raise FileNotFoundError(
            f"Transcript not found: "
            f"{transcript_path}"
        )

    with open(
        transcript_path,
        "r",
        encoding="utf-8"
    ) as file:

        transcript = json.load(file)

    if not transcript.get("segments"):

        raise ValueError(
            "Transcript contains no speech segments."
        )

    return transcript


def extract_clip_words(
    transcript: dict,
    clip_start: float,
    clip_end: float,
    clip_duration: float
) -> list:
    """
    Extract words belonging to a clip
    and convert their timestamps into
    clip-relative timestamps.
    """

    clip_start = float(clip_start)
    clip_end = float(clip_end)
    clip_duration = float(clip_duration)

    if not all(
        math.isfinite(value)
        for value in (
            clip_start,
            clip_end,
            clip_duration
        )
    ):

        raise ValueError(
            "Invalid clip timestamps."
        )

    if (
        clip_start < 0
        or clip_end <= clip_start
        or clip_duration <= 0
    ):

        raise ValueError(
            "Invalid clip time range."
        )

    words = []

    # Read all word-level timestamps
    for segment in transcript["segments"]:

        for word in segment.get("words", []):

            text = str(
                word.get("word", "")
            ).strip()

            if not text:

                continue

            start = float(word["start"])
            end = float(word["end"])

            if not (
                math.isfinite(start)
                and math.isfinite(end)
            ):

                continue

            if end <= start:

                continue

            # Ignore words outside this clip
            if (
                end <= clip_start
                or start >= clip_end
            ):

                continue

            # Shift timestamps to the clip
            relative_start = max(
                0.0,
                start - clip_start
            )

            relative_end = min(
                clip_duration,
                clip_end - clip_start,
                end - clip_start
            )

            if relative_end <= relative_start:

                continue

            words.append({
                "word": text,
                "start": relative_start,
                "end": relative_end
            })

    # Ensure chronological ordering
    words.sort(
        key=lambda word: (
            word["start"],
            word["end"]
        )
    )

    # Prevent overlapping word timestamps
    normalized_words = []

    previous_end = 0.0

    for word in words:

        start = max(
            word["start"],
            previous_end
        )

        end = word["end"]

        if end - start < 0.01:

            continue

        normalized_words.append({
            "word": word["word"],
            "start": start,
            "end": end
        })

        previous_end = end

    if not normalized_words:

        raise ValueError(
            "No word-level timestamps were "
            "found inside this clip."
        )

    return normalized_words


def group_caption_words(
    words: list,
    max_words: int = 4,
    max_characters: int = 28,
    max_duration: float = 2.5,
    max_gap: float = 0.45
) -> list:
    """
    Divide words into short caption groups.

    Captions are split at:
    - Word count limits
    - Character count limits
    - Long speech pauses
    - Duration limits
    - Sentence endings
    """

    if (
        max_words < 1
        or max_characters < 1
        or max_duration <= 0
        or max_gap < 0
    ):

        raise ValueError(
            "Invalid caption grouping settings."
        )

    groups = []

    current_words = []

    def finish_group():

        if not current_words:

            return

        groups.append({
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": " ".join(
                word["word"]
                for word in current_words
            ),
            "words": current_words.copy()
        })

        current_words.clear()

    for word in words:

        if current_words:

            previous_word = current_words[-1]

            proposed_text = " ".join(
                item["word"]
                for item in (
                    current_words + [word]
                )
            )

            proposed_duration = (
                word["end"]
                - current_words[0]["start"]
            )

            speech_gap = (
                word["start"]
                - previous_word["end"]
            )

            sentence_finished = (
                previous_word["word"]
                .rstrip("\"'")
                .endswith((".", "?", "!"))
            )

            should_split = (
                len(current_words) >= max_words
                or len(proposed_text)
                > max_characters
                or proposed_duration > max_duration
                or speech_gap > max_gap
                or sentence_finished
            )

            if should_split:

                finish_group()

        current_words.append(word)

    finish_group()

    return groups


def format_srt_timestamp(
    seconds: float
) -> str:
    """
    Convert seconds into SRT timestamp format.

    Example: 00:00:01,500
    """

    milliseconds = max(
        0,
        round(seconds * 1000)
    )

    hours, remainder = divmod(
        milliseconds,
        3600000
    )

    minutes, remainder = divmod(
        remainder,
        60000
    )

    secs, ms = divmod(
        remainder,
        1000
    )

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{ms:03d}"
    )


def format_ass_timestamp(
    seconds: float
) -> str:
    """
    Convert seconds into ASS timestamp format.

    Example: 0:00:01.50
    """

    centiseconds = max(
        0,
        round(seconds * 100)
    )

    hours, remainder = divmod(
        centiseconds,
        360000
    )

    minutes, remainder = divmod(
        remainder,
        6000
    )

    secs, cs = divmod(
        remainder,
        100
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{cs:02d}"
    )


def write_srt_file(
    groups: list,
    output_path: str
) -> Path:
    """
    Create a standard SRT subtitle file.
    """

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    lines = []

    for index, group in enumerate(
        groups,
        start=1
    ):

        start = format_srt_timestamp(
            group["start"]
        )

        end = format_srt_timestamp(
            group["end"]
        )

        lines.extend([
            str(index),
            f"{start} --> {end}",
            group["text"],
            ""
        ])

    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    return output_path


def sanitize_ass_text(
    text: str
) -> str:
    """
    Prevent transcript text from being
    interpreted as ASS formatting commands.
    """

    return (
        text
        .replace("\\", "＼")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def split_caption_lines(
    words: list,
    max_line_characters: int = 18
) -> list:
    """
    Split caption words into short lines
    while preserving word indexes.
    """

    lines = []

    current_line = []

    current_length = 0

    for index, word in enumerate(words):

        text = word["word"]

        added_length = len(text)

        if current_line:

            added_length += 1

        if (
            current_line
            and current_length + added_length
            > max_line_characters
        ):

            lines.append(current_line)

            current_line = []

            current_length = 0

        if current_line:

            current_length += 1

        current_line.append(index)

        current_length += len(text)

    if current_line:

        lines.append(current_line)

    return lines


def build_ass_caption_text(
    words: list,
    active_index=None,
    uppercase: bool = True
) -> str:
    """
    Build styled ASS caption text.

    The active word is yellow.
    All other words use the default color.
    """

    display_words = []

    for word in words:

        text = sanitize_ass_text(
            word["word"]
        )

        if uppercase:

            text = text.upper()

        display_words.append({
            "word": text
        })

    line_indexes = split_caption_lines(
        display_words
    )

    rendered_lines = []

    for indexes in line_indexes:

        rendered_words = []

        for index in indexes:

            text = display_words[index]["word"]

            if index == active_index:

                # ASS uses BGR color order.
                # This value produces yellow.
                text = (
                    r"{\1c&H0000FFFF&}"
                    + text
                    + r"{\1c}"
                )

            rendered_words.append(text)

        rendered_lines.append(
            " ".join(rendered_words)
        )

    # ASS line break
    return r"\N".join(rendered_lines)


def write_ass_file(
    groups: list,
    output_path: str,
    style: str = "word_highlight",
    width: int = 720,
    height: int = 1280
) -> Path:
    """
    Generate styled ASS subtitles.

    Supported styles:
    - word_highlight
    - classic
    - bold_yellow
    """

    if style not in SUPPORTED_STYLES:

        raise ValueError(
            f"Unsupported caption style: {style}"
        )

    if width <= 0 or height <= 0:

        raise ValueError(
            "Invalid video dimensions."
        )

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Scale caption settings for resolution
    scale = height / 1280

    font_size = round(52 * scale)

    outline = round(4 * scale)

    shadow = round(2 * scale)

    margin_horizontal = round(
        50 * width / 720
    )

    margin_vertical = round(
        260 * scale
    )

    primary_color = "&H00FFFFFF"

    border_style = 1

    uppercase = True

    if style == "classic":

        font_size = round(42 * scale)

        uppercase = False

        border_style = 3

        outline = round(6 * scale)

        shadow = 0

    elif style == "bold_yellow":

        primary_color = "&H0000FFFF"

    # ASS subtitle header
    header = f"""[Script Info]
Title: ClipMind AI Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{primary_color},&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,{border_style},{outline},{shadow},2,{margin_horizontal},{margin_horizontal},{margin_vertical},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    def add_event(
        start: float,
        end: float,
        text: str
    ):

        start_time = format_ass_timestamp(
            start
        )

        end_time = format_ass_timestamp(
            end
        )

        # Ignore zero-length subtitle events
        if (
            end <= start
            or start_time == end_time
        ):

            return

        events.append(
            f"Dialogue: 0,"
            f"{start_time},"
            f"{end_time},"
            f"Default,,0,0,0,,"
            f"{text}"
        )

    for group in groups:

        words = group["words"]

        if style == "word_highlight":

            # Create an event for each spoken word.
            # The complete group remains visible.
            # Only the active word changes color.

            for index, word in enumerate(words):

                start = word["start"]

                end = word["end"]

                text = build_ass_caption_text(
                    words=words,
                    active_index=index,
                    uppercase=uppercase
                )

                add_event(
                    start,
                    end,
                    text
                )

                # Keep the caption visible in
                # short gaps between spoken words.
                if index + 1 < len(words):

                    next_start = (
                        words[index + 1]["start"]
                    )

                    if next_start > end:

                        neutral_text = (
                            build_ass_caption_text(
                                words=words,
                                active_index=None,
                                uppercase=uppercase
                            )
                        )

                        add_event(
                            end,
                            next_start,
                            neutral_text
                        )

        else:

            text = build_ass_caption_text(
                words=words,
                active_index=None,
                uppercase=uppercase
            )

            add_event(
                group["start"],
                group["end"],
                text
            )

    if not events:

        raise ValueError(
            "No subtitle events were generated."
        )

    output_path.write_text(
        header + "\n".join(events) + "\n",
        encoding="utf-8-sig"
    )

    return output_path


def burn_captions_into_video(
    input_path: str,
    ass_path: str,
    output_path: str
) -> dict:
    """
    Permanently render styled captions
    into an MP4 video using FFmpeg.
    """

    input_path = Path(input_path).resolve()

    ass_path = Path(ass_path).resolve()

    output_path = Path(output_path).resolve()

    if not input_path.is_file():

        raise FileNotFoundError(
            f"Input video not found: {input_path}"
        )

    if not ass_path.is_file():

        raise FileNotFoundError(
            f"ASS subtitle file not found: "
            f"{ass_path}"
        )

    if input_path == output_path:

        raise ValueError(
            "Input and output videos must "
            "be different."
        )

    if output_path.suffix.lower() != ".mp4":

        raise ValueError(
            "Output video must use MP4 format."
        )

    # Require a safe subtitle filename.
    # This avoids FFmpeg filter escaping
    # problems on Windows.
    if not all(
        character.isascii()
        and (
            character.isalnum()
            or character in "._-"
        )
        for character in ass_path.name
    ):

        raise ValueError(
            "Subtitle filename must contain "
            "only letters, numbers, dots, "
            "underscores or hyphens."
        )

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

    temp_path = output_path.with_name(
        f"{output_path.stem}.partial.mp4"
    )

    if temp_path == input_path:

        raise ValueError(
            "Temporary output conflicts "
            "with the input video."
        )

    # Use the subtitle directory as FFmpeg's
    # working directory. This avoids passing
    # a Windows drive letter into the ASS filter.
    subtitle_filter = (
        f"ass=filename={ass_path.name}"
    )

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel", "error",

        "-y",

        "-i", str(input_path),

        "-map", "0:v:0",

        "-map", "0:a:0?",

        "-filter_threads", "4",

        "-vf", subtitle_filter,

        "-c:v", "libx264",

        "-preset", "fast",

        "-crf", "21",

        "-pix_fmt", "yuv420p",

        # Preserve the existing AAC audio
        # without another encoding pass.
        "-c:a", "copy",

        "-threads", "4",

        "-movflags", "+faststart",

        str(temp_path)
    ]

    try:

        print(
            f"\nRendering captions: "
            f"{input_path.name}"
        )

        start_time = time.perf_counter()

        subprocess.run(
            command,
            cwd=str(ass_path.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=600
        )

        if not temp_path.is_file():

            raise RuntimeError(
                "Captioned video was not created."
            )

        if temp_path.stat().st_size == 0:

            raise RuntimeError(
                "Captioned video is empty."
            )

        metadata = get_video_metadata(
            str(temp_path)
        )

        # Validate resolution
        if (
            metadata["width"]
            != source_metadata["width"]
            or metadata["height"]
            != source_metadata["height"]
        ):

            raise RuntimeError(
                "Video resolution changed "
                "during caption rendering."
            )

        # Validate duration
        if abs(
            metadata["duration_seconds"]
            - source_metadata["duration_seconds"]
        ) > 0.5:

            raise RuntimeError(
                "Video duration changed "
                "during caption rendering."
            )

        if metadata["video_codec"] != "h264":

            raise RuntimeError(
                "Incorrect output video codec."
            )

        # Validate audio preservation
        if (
            metadata["has_audio"]
            != source_metadata["has_audio"]
        ):

            raise RuntimeError(
                "Audio availability changed "
                "during caption rendering."
            )

        if (
            source_metadata["has_audio"]
            and metadata["audio_codec"]
            != source_metadata["audio_codec"]
        ):

            raise RuntimeError(
                "Audio codec changed "
                "unexpectedly."
            )

        temp_path.replace(output_path)

        elapsed_time = (
            time.perf_counter() - start_time
        )

        result = {
            "status": "success",
            "filename": output_path.name,
            "file_path": str(output_path),
            "resolution": metadata["resolution"],
            "duration_seconds": (
                metadata["duration_seconds"]
            ),
            "video_codec": metadata["video_codec"],
            "audio_codec": metadata["audio_codec"],
            "has_audio": metadata["has_audio"],
            "size_mb": metadata["size_mb"],
            "processing_time_seconds": round(
                elapsed_time,
                2
            )
        }

        print(
            f"Captioned video created: "
            f"{output_path.name}"
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
            f"FFmpeg caption rendering failed: "
            f"{error.stderr}"
        ) from error

    except subprocess.TimeoutExpired as error:

        raise RuntimeError(
            "Caption rendering timed out."
        ) from error

    finally:

        if temp_path.exists():

            temp_path.unlink()


def generate_captioned_clip(
    input_path: str,
    transcript: dict,
    clip_start: float,
    clip_end: float,
    output_dir: str,
    style: str = "word_highlight"
) -> dict:
    """
    Generate subtitle files and a
    captioned MP4 for one video clip.
    """

    if style not in SUPPORTED_STYLES:

        raise ValueError(
            f"Unsupported caption style: {style}"
        )

    input_path = Path(input_path)

    output_dir = Path(output_dir)

    if not input_path.is_file():

        raise FileNotFoundError(
            f"Input clip not found: {input_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    metadata = get_video_metadata(
        str(input_path)
    )

    if not metadata.get("video_codec"):

        raise ValueError(
            "Input file contains no video."
        )

    # Extract clip-relative word timestamps
    words = extract_clip_words(
        transcript=transcript,
        clip_start=clip_start,
        clip_end=clip_end,
        clip_duration=metadata[
            "duration_seconds"
        ]
    )

    # Build short caption groups
    groups = group_caption_words(
        words=words
    )

    print(
        f"\nWords extracted: {len(words)}"
    )

    print(
        f"Caption groups: {len(groups)}"
    )

    print(
        f"Caption style: {style}"
    )

    # Output filenames
    base_name = (
        f"{input_path.stem}_{style}"
    )

    srt_path = (
        output_dir
        / f"{base_name}.srt"
    )

    ass_path = (
        output_dir
        / f"{base_name}.ass"
    )

    video_path = (
        output_dir
        / f"{base_name}_captioned.mp4"
    )

    # Generate editable standard subtitles
    write_srt_file(
        groups=groups,
        output_path=str(srt_path)
    )

    # Generate styled subtitles
    write_ass_file(
        groups=groups,
        output_path=str(ass_path),
        style=style,
        width=metadata["width"],
        height=metadata["height"]
    )

    print(
        f"SRT subtitles created: "
        f"{srt_path.name}"
    )

    print(
        f"ASS subtitles created: "
        f"{ass_path.name}"
    )

    # Burn subtitles into the video
    result = burn_captions_into_video(
        input_path=str(input_path),
        ass_path=str(ass_path),
        output_path=str(video_path)
    )

    result["source_filename"] = (
        input_path.name
    )

    result["caption_style"] = style

    result["total_words"] = len(words)

    result["caption_groups"] = len(groups)

    result["srt_path"] = str(srt_path)

    result["ass_path"] = str(ass_path)

    result["start"] = float(clip_start)

    result["end"] = float(clip_end)

    return result


def generate_captioned_clips(
    vertical_report_path: str,
    style: str = "word_highlight"
) -> dict:
    """
    Generate captions for every clip
    listed in a vertical_report.json file.
    """

    if style not in SUPPORTED_STYLES:

        raise ValueError(
            f"Unsupported caption style: {style}"
        )

    vertical_report_path = Path(
        vertical_report_path
    )

    if not vertical_report_path.is_file():

        raise FileNotFoundError(
            f"Vertical report not found: "
            f"{vertical_report_path}"
        )

    with open(
        vertical_report_path,
        "r",
        encoding="utf-8"
    ) as file:

        vertical_report = json.load(file)

    clips = vertical_report.get(
        "clips",
        []
    )

    if not clips:

        raise ValueError(
            "Vertical report contains no clips."
        )

    source_video = vertical_report.get(
        "source_video"
    )

    if not source_video:

        raise ValueError(
            "Vertical report does not identify "
            "the original source video."
        )

    # Match the original transcript
    source_stem = Path(
        source_video
    ).stem

    transcript_path = (
        TRANSCRIPT_DIR
        / f"{source_stem}.json"
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
            "the source video."
        )

    # Preserve all original vertical videos
    output_dir = (
        vertical_report_path.parent
        / "captioned"
        / style
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n" + "=" * 60)

    print("CLIPMIND AI - CAPTION GENERATION")

    print("=" * 60)

    print(
        f"\nSource video: {source_video}"
    )

    print(
        f"Transcript: {transcript_path.name}"
    )

    print(
        f"Caption style: {style}"
    )

    print(
        f"Clips to process: {len(clips)}"
    )

    successful_clips = []

    failed_clips = []

    start_time = time.perf_counter()

    for index, clip in enumerate(
        clips,
        start=1
    ):

        print("\n" + "-" * 50)

        print(
            f"Captioning clip "
            f"{index}/{len(clips)}"
        )

        try:

            input_path = (
                vertical_report_path.parent
                / Path(clip["filename"]).name
            )

            result = generate_captioned_clip(
                input_path=str(input_path),
                transcript=transcript,
                clip_start=clip["start"],
                clip_end=clip["end"],
                output_dir=str(output_dir),
                style=style
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

            successful_clips.append(result)

        except Exception as error:

            failed_clips.append({
                "clip_id": clip.get(
                    "clip_id",
                    index
                ),
                "error": str(error)
            })

            print(
                f"Caption generation failed: "
                f"{error}"
            )

    elapsed_time = (
        time.perf_counter() - start_time
    )

    if not successful_clips:

        status = "failed"

    elif failed_clips:

        status = "partial_success"

    else:

        status = "success"

    total_size_mb = round(
        sum(
            clip["size_mb"]
            for clip in successful_clips
        ),
        2
    )

    report = {
        "status": status,
        "source_video": source_video,
        "source_transcript": str(
            transcript_path
        ),
        "source_vertical_report": str(
            vertical_report_path
        ),
        "caption_style": style,
        "requested_clips": len(clips),
        "captioned_clips": len(
            successful_clips
        ),
        "failed_clips": len(
            failed_clips
        ),
        "total_size_mb": total_size_mb,
        "processing_time_seconds": round(
            elapsed_time,
            2
        ),
        "output_directory": str(
            output_dir
        ),
        "clips": successful_clips,
        "errors": failed_clips
    }

    report_path = (
        output_dir
        / "caption_report.json"
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

    print("\n" + "=" * 60)

    print("CAPTION GENERATION COMPLETE")

    print("=" * 60)

    print(
        f"Status: {status}"
    )

    print(
        f"Captioned clips: "
        f"{len(successful_clips)}"
    )

    print(
        f"Failed clips: "
        f"{len(failed_clips)}"
    )

    print(
        f"Total output size: "
        f"{total_size_mb} MB"
    )

    print(
        f"Total processing time: "
        f"{elapsed_time:.2f} seconds"
    )

    print(
        f"\nOutput folder: {output_dir}"
    )

    return report
