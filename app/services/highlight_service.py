
import json
import re
from pathlib import Path


# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent

HIGHLIGHT_DIR = (
    BASE_DIR / "storage" / "temp" / "highlights"
)

HIGHLIGHT_DIR.mkdir(parents=True, exist_ok=True)


# Words and phrases that may indicate
# interesting or emotional moments

HOOK_PHRASES = [
    "did you know",
    "what if",
    "the truth is",
    "the secret",
    "you won't believe",
    "here's why",
    "listen",
    "imagine",
    "the reason",
    "let me tell you",
    "you need to",
    "what happened",
    "why would",
    "how did",
    "the problem is"
]

EMOTIONAL_WORDS = [
    "love",
    "hate",
    "fear",
    "angry",
    "anger",
    "happy",
    "sad",
    "shocked",
    "surprised",
    "amazing",
    "incredible",
    "terrible",
    "danger",
    "dangerous",
    "death",
    "killed",
    "killer",
    "murder",
    "truth",
    "secret",
    "betrayal",
    "revenge",
    "trust",
    "believe",
    "sorry",
    "never",
    "impossible",
    "important",
    "seriously",
    "trouble"
]

CURIOSITY_WORDS = [
    "why",
    "how",
    "what",
    "who",
    "where",
    "when",
    "really",
    "actually",
    "because",
    "remember",
    "understand",
    "discover",
    "explain",
    "realize"
]


def count_matches(text: str, phrases: list) -> int:
    """
    Count matching words or phrases
    without matching partial words.
    """

    text = text.lower()

    total = 0

    for phrase in phrases:

        pattern = (
            r"\b" + re.escape(phrase) + r"\b"
        )

        matches = re.findall(pattern, text)

        total += len(matches)

    return total


def calculate_highlight_score(
    text: str,
    duration: float,
    first_text: str
) -> dict:
    """
    Calculate a heuristic highlight score.

    The final score is between 0 and 100.
    """

    words = re.findall(r"\b\w+\b", text)

    word_count = len(words)

    if duration <= 0 or word_count == 0:

        return {
            "score": 0,
            "hook_score": 0,
            "emotion_score": 0,
            "curiosity_score": 0,
            "speech_score": 0,
            "structure_score": 0
        }

    # 1. Opening hook score
    hook_matches = count_matches(
        first_text,
        HOOK_PHRASES
    )

    hook_score = min(
        25,
        hook_matches * 10
    )

    # Reward questions near the beginning
    if "?" in first_text:

        hook_score = min(
            25,
            hook_score + 8
        )

    # 2. Emotional language score
    emotion_matches = count_matches(
        text,
        EMOTIONAL_WORDS
    )

    emotion_score = min(
        25,
        emotion_matches * 4
    )

    # 3. Curiosity score
    curiosity_matches = count_matches(
        text,
        CURIOSITY_WORDS
    )

    curiosity_score = min(
        20,
        curiosity_matches * 3
    )

    # 4. Speech density score
    words_per_second = word_count / duration

    if 1.5 <= words_per_second <= 3.5:

        speech_score = 20

    elif 1.0 <= words_per_second < 1.5:

        speech_score = 14

    elif 3.5 < words_per_second <= 4.5:

        speech_score = 14

    elif words_per_second < 1.0:

        speech_score = 5

    else:

        speech_score = 8

    # 5. Sentence structure score
    structure_score = 0

    if text.strip().endswith(
        (".", "?", "!")
    ):

        structure_score += 5

    if word_count >= 25:

        structure_score += 5

    # Calculate total score
    total_score = (
        hook_score
        + emotion_score
        + curiosity_score
        + speech_score
        + structure_score
    )

    return {
        "score": round(
            min(100, total_score),
            2
        ),
        "hook_score": hook_score,
        "emotion_score": emotion_score,
        "curiosity_score": curiosity_score,
        "speech_score": speech_score,
        "structure_score": structure_score
    }


def generate_candidates(
    segments: list,
    min_duration: float = 20,
    max_duration: float = 30
) -> list:
    """
    Build fixed-length highlight windows without requiring transcript
    segment boundaries to land exactly on the requested duration.

    Each window stays within the transcribed time range. Word-level
    timestamps are used for candidate text when available; otherwise
    overlapping segment text is used.
    """
    valid_segments = []
    for segment in segments:
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            valid_segments.append((start, end, segment))

    if not valid_segments:
        return []

    valid_segments.sort(key=lambda item: item[0])
    last_end = max(item[1] for item in valid_segments)
    first_start = valid_segments[0][0]

    # Include natural speech starts plus regularly spaced starts,
    # so long transcription segments still yield useful windows.
    step = max(5.0, min_duration / 2.0)
    starts = {item[0] for item in valid_segments}
    current = first_start
    while current + min_duration <= last_end + 1e-6:
        starts.add(current)
        current += step

    candidates = []
    seen = set()

    for start_time in sorted(starts):
        end_time = min(start_time + max_duration, last_end)
        duration = end_time - start_time
        if duration + 1e-6 < min_duration:
            continue

        # Avoid duplicates caused by very close starting timestamps.
        key = (round(start_time, 2), round(end_time, 2))
        if key in seen:
            continue
        seen.add(key)

        parts = []
        for seg_start, seg_end, segment in valid_segments:
            if seg_end <= start_time or seg_start >= end_time:
                continue

            words = segment.get("words")
            if isinstance(words, list) and words:
                selected_words = []
                for word in words:
                    try:
                        word_start = float(word["start"])
                        word_end = float(word["end"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if word_end > start_time and word_start < end_time:
                        selected_words.append(str(word.get("word", "")))
                piece = "".join(selected_words).strip()
                if not piece:
                    piece = str(segment.get("text", "")).strip()
            else:
                piece = str(segment.get("text", "")).strip()

            if piece:
                parts.append(piece)

        if not parts:
            continue

        text = " ".join(parts)
        score_data = calculate_highlight_score(
            text=text,
            duration=duration,
            first_text=parts[0]
        )
        candidates.append({
            "start": round(start_time, 2),
            "end": round(end_time, 2),
            "duration": round(duration, 2),
            "text": text,
            "score": score_data["score"],
            "score_details": score_data
        })

    return candidates


def clips_overlap(
    first_clip: dict,
    second_clip: dict
) -> bool:
    """
    Check whether two candidate clips overlap.
    """

    return (
        first_clip["start"] < second_clip["end"]
        and
        first_clip["end"] > second_clip["start"]
    )


def select_best_highlights(
    candidates: list,
    clip_count: int = 5
) -> list:
    """
    Select the highest-scoring clips
    while avoiding overlapping timestamps.
    """

    ranked_candidates = sorted(
        candidates,
        key=lambda clip: clip["score"],
        reverse=True
    )

    selected = []

    for candidate in ranked_candidates:

        has_overlap = any(
            clips_overlap(candidate, existing)
            for existing in selected
        )

        if has_overlap:

            continue

        selected.append(candidate)

        if len(selected) >= clip_count:

            break

    # Assign clip IDs and basic titles
    for index, clip in enumerate(
        selected,
        start=1
    ):

        clip["clip_id"] = index

        clip["title"] = (
            f"Highlight {index}"
        )

    return selected


def detect_highlights(
    transcript_path: str,
    clip_count: int = 5,
    min_duration: float = 20,
    max_duration: float = 30
) -> dict:
    """
    Detect and rank highlight clips
    from a timestamped transcript.
    """

    transcript_path = Path(transcript_path)

    if not transcript_path.is_file():

        raise FileNotFoundError(
            f"Transcript not found: "
            f"{transcript_path}"
        )

    if clip_count < 1:

        raise ValueError(
            "Clip count must be at least 1."
        )

    if min_duration <= 0:

        raise ValueError(
            "Minimum duration must be positive."
        )

    if max_duration < min_duration:

        raise ValueError(
            "Maximum duration must be greater "
            "than or equal to minimum duration."
        )

    # Load transcript JSON
    with open(
        transcript_path,
        "r",
        encoding="utf-8"
    ) as file:

        transcript = json.load(file)

    segments = transcript.get(
        "segments",
        []
    )

    if not segments:

        raise ValueError(
            "Transcript contains no speech segments."
        )

    print("\nAnalyzing transcript...")
    print(f"Speech segments: {len(segments)}")

    print(
        f"Requested clips: {clip_count}"
    )

    print(
        f"Clip duration: "
        f"{min_duration}-{max_duration} seconds"
    )

    # Generate possible highlight clips
    candidates = generate_candidates(
        segments=segments,
        min_duration=min_duration,
        max_duration=max_duration
    )

    print(
        f"\nCandidate clips generated: "
        f"{len(candidates)}"
    )

    if not candidates:

        raise ValueError(
            "No suitable clip candidates found. "
            "Try a shorter minimum duration."
        )

    # Select best non-overlapping clips
    highlights = select_best_highlights(
        candidates=candidates,
        clip_count=clip_count
    )

    # Prepare final results
    result = {
        "status": "success",
        "source_transcript": transcript_path.name,
        "language": transcript.get("language"),
        "video_duration_seconds": transcript.get(
            "duration_seconds"
        ),
        "scoring_method": "heuristic_v1",
        "total_candidates": len(candidates),
        "requested_clips": clip_count,
        "selected_clips": len(highlights),
        "min_clip_duration": min_duration,
        "max_clip_duration": max_duration,
        "highlights": highlights
    }

    # Save highlight results
    output_path = (
        HIGHLIGHT_DIR
        / f"{transcript_path.stem}_highlights.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"\nSelected highlights: "
        f"{len(highlights)}"
    )

    print(
        f"Highlights saved to: {output_path}"
    )

    result["highlights_path"] = str(
        output_path
    )

    return result
