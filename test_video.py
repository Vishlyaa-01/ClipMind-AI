
from pathlib import Path
from app.services.video_service import get_video_metadata
import json

# Locate the uploads folder
UPLOAD_DIR = Path(__file__).resolve().parent / "storage" / "uploads"

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

    print("\nAnalyzing video...\n")

    metadata = get_video_metadata(str(video_path))

    print("Video metadata:")
    print(json.dumps(metadata, indent=4))

    print("\nVideo analysis completed successfully!")
