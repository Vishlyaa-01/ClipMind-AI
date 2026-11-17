
import os
import json
import time
import wave
from pathlib import Path

import numpy as np


# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent

MODEL_DIR = BASE_DIR / "models" / "whisper"

TRANSCRIPT_DIR = (
    BASE_DIR / "storage" / "temp" / "transcripts"
)

# Create directories automatically
MODEL_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

# Keep Hugging Face cache on the D: drive
os.environ["HF_HOME"] = str(
    BASE_DIR / "models" / "huggingface"
)

from faster_whisper import WhisperModel


# Model configuration
MODEL_SIZE = "base"

# Keep the model in memory after loading
_model = None


def load_model():
    """
    Load the local Whisper AI model.
    """

    global _model

    if _model is None:

        print("Loading Whisper AI model...")
        print(f"Model: {MODEL_SIZE}")
        print("Device: CPU")
        print("Compute type: INT8")

        _model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            download_root=str(MODEL_DIR)
        )

        print("Whisper model loaded successfully!")

    return _model


def load_wav_audio(audio_path: str) -> np.ndarray:
    """
    Read a 16 kHz mono PCM WAV file directly.

    This bypasses PyAV audio decoding and
    returns a normalized float32 NumPy array.
    """

    with wave.open(str(audio_path), "rb") as wav_file:

        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()

        if sample_rate != 16000:
            raise ValueError(
                "Audio must have a sample rate of 16000 Hz."
            )

        if channels != 1:
            raise ValueError(
                "Audio must be mono."
            )

        if sample_width != 2:
            raise ValueError(
                "Audio must use 16-bit PCM."
            )

        if frame_count == 0:
            raise ValueError(
                "Audio file is empty."
            )

        # Read raw PCM audio samples
        raw_audio = wav_file.readframes(frame_count)

    # Convert 16-bit PCM to float32
    audio = np.frombuffer(
        raw_audio,
        dtype="<i2"
    ).astype(np.float32)

    # Normalize samples to approximately -1.0 to 1.0
    audio /= 32768.0

    if audio.size == 0:
        raise ValueError(
            "No audio samples were loaded."
        )

    return audio


def transcribe_audio(audio_path: str) -> dict:
    """
    Convert audio into timestamped text
    using the local Faster-Whisper model.
    """

    audio_path = Path(audio_path)

    if not audio_path.is_file():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    # Load WAV audio directly
    print("\nReading WAV audio directly...")

    audio_data = load_wav_audio(str(audio_path))

    audio_duration = len(audio_data) / 16000

    print(
        f"Audio duration: {audio_duration:.2f} seconds"
    )

    print("Audio loaded successfully!")

    # Load AI model
    model = load_model()

    print("\nStarting AI transcription...")
    print("This may take several minutes.\n")

    start_time = time.time()

    # Pass NumPy audio directly to Whisper
    # This avoids the PyAV decoding issue
    segments, info = model.transcribe(
        audio_data,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True
    )

    transcript_segments = []
    full_text = []

    # Process timestamped segments
    for segment in segments:

        segment_data = {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
            "words": [
                {
                    "start": round(word.start, 2),
                    "end": round(word.end, 2),
                    "word": word.word.strip()
                }
                for word in (segment.words or [])
            ]
        }

        transcript_segments.append(segment_data)

        full_text.append(segment.text.strip())

        print(
            f"[{segment.start:.2f}s - "
            f"{segment.end:.2f}s] "
            f"{segment.text.strip()}"
        )

    elapsed_time = time.time() - start_time

    # Prepare final transcript
    transcript = {
        "status": "success",
        "audio_filename": audio_path.name,
        "model": MODEL_SIZE,
        "language": info.language,
        "language_probability": round(
            info.language_probability, 4
        ),
        "duration_seconds": round(info.duration, 2),
        "total_segments": len(transcript_segments),
        "processing_time_seconds": round(
            elapsed_time, 2
        ),
        "full_text": " ".join(full_text),
        "segments": transcript_segments
    }

    # Save transcript as JSON
    transcript_path = (
        TRANSCRIPT_DIR / f"{audio_path.stem}.json"
    )

    with open(
        transcript_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            transcript,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\nTranscription completed successfully!")
    print(f"Transcript saved to: {transcript_path}")

    return {
        "status": "success",
        "transcript_filename": transcript_path.name,
        "transcript_path": str(transcript_path),
        "language": info.language,
        "duration_seconds": round(info.duration, 2),
        "total_segments": len(transcript_segments),
        "processing_time_seconds": round(
            elapsed_time, 2
        )
    }
