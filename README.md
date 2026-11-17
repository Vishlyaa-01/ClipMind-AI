# ClipMind AI 🎬

**Turn long videos into short, shareable vertical clips using AI.**

ClipMind AI is a locally running, AI-powered video clipping application built with Python, FastAPI, FFmpeg, and Faster-Whisper. It analyzes videos, identifies highlight segments, and generates vertical Shorts suitable for platforms such as YouTube Shorts, Instagram Reels, and TikTok.

## Features

- **Video Uploads:** Import videos from your computer.
- **YouTube URL Import:** Import supported YouTube videos using yt-dlp.
- **AI Transcription:** Transcribe video audio using Faster-Whisper.
- **Highlight Detection:** Identify candidate moments for short clips.
- **Automatic Clip Generation:** Generate multiple Shorts from a source video.
- **Vertical Video Conversion:** Produce 9:16 videos at 720 × 1280 resolution.
- **Optional Captions:** Enable synchronized AI-generated captions or leave them disabled by default.
- **Web Dashboard:** Dark-themed interface with processing progress.
- **Video Preview and Download:** Watch and download generated MP4 files.
- **Job History:** Restore previously completed processing jobs.

## Technology Stack

- Python 3.12
- FastAPI
- Uvicorn
- Faster-Whisper
- NumPy
- FFmpeg
- yt-dlp
- HTML, CSS, and JavaScript

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ClipMind-AI.git
cd ClipMind-AI
```

Replace `YOUR_USERNAME` with your GitHub username.

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Install FFmpeg

Install FFmpeg separately and make sure `ffmpeg` and `ffprobe` are available in your system PATH.

Verify:

```powershell
ffmpeg -version
ffprobe -version
```

### 5. Start the application

```powershell
python -m uvicorn app.main:app --reload
```

Open the dashboard:

**http://127.0.0.1:8000**

## How to Use

1. Upload a video or paste a supported YouTube URL.
2. Choose the clip duration and number of Shorts.
3. Leave **Enable Captions** unchecked for clean videos, or check it to generate subtitles.
4. Click **Generate AI Clips**.
5. Wait for processing to complete.
6. Preview and download the generated MP4 Shorts.

## Project Structure

```text
ClipMind-AI/
├── app/
│   ├── main.py
│   └── services/
│       ├── audio_service.py
│       ├── caption_service.py
│       ├── clip_service.py
│       ├── highlight_service.py
│       ├── job_service.py
│       ├── pipeline_service.py
│       ├── transcription_service.py
│       ├── vertical_service.py
│       ├── video_service.py
│       └── youtube_service.py
├── frontend/
│   └── index.html
├── requirements.txt
├── .gitignore
└── README.md
```

## Notes

- Processing is performed locally and may take time, depending on video length and computer performance.
- AI model files are downloaded or cached locally and are not included in this repository.
- The number of generated clips depends on available highlight segments.
- Automatic captions may contain transcription errors, especially with multilingual audio.
- Only download or process videos you own or are authorized to use.

## Project Status

**Working local prototype — under active development.**

The application has been tested with video imports, AI processing, and generated vertical Shorts. Longer-video performance and broader compatibility require further testing.
