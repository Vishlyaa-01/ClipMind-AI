
from pathlib import Path
from app.services.audio_service import extract_audio
from app.services.video_service import get_video_metadata
import json
import time


# Locate the uploads folder
UPLOAD_DIR = (
    Path(__file__).resolve().parent
    / "storage"
    / "uploads"
)

# Find uploaded video files
video_files = [
    file for file in UPLOAD_DIR.iterdir()
    if file.is_file()
    and file.suffix.lower() in {
        ".mp4", ".mkv", ".mov", ".avi", ".webm"
    }
]

if not video_files:
    print("No video files found in the uploads folder.")

else:
    # Select the most recently modified video
    video_path = max(
        video_files,
        key=lambda file: file.stat().st_mtime
    )

    print("Testing video:")
    print(video_path)

    try:
        # Check whether the video has audio
        metadata = get_video_metadata(str(video_path))

        if not metadata["has_audio"]:
            print("\nThis video does not contain audio.")

        else:
            print("\nExtracting audio...")
            print("Please wait...\n")

            start_time = time.time()

            # Extract audio using FFmpeg
            result = extract_audio(str(video_path))

            elapsed_time = time.time() - start_time

            print("Audio extraction result:")
            print(json.dumps(result, indent=4))

            print(
                f"\nProcessing time: "
                f"{elapsed_time:.2f} seconds"
            )

            print(
                "\nAudio extraction completed successfully!"
            )

    except Exception as error:
        print(f"\nError: {error}")
