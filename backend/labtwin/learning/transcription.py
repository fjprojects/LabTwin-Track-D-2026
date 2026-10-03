"""Bounded media conversion and timestamped speech extraction."""
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from .access import LearningError


def embedded_transcript(path):
    """Automatically use caption tracks shipped inside a lecture upload."""
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries", "stream=index", "-of", "json", str(path)], capture_output=True, timeout=20, check=True)
        if not json.loads(probe.stdout).get("streams"):
            return None
        duration = media_info(path)
        result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:s:0", "-f", "webvtt", "-"], capture_output=True, timeout=30, check=True)
        text = result.stdout.decode("utf-8", errors="replace")
        def seconds(value):
            parts = value.split(":")
            return sum(float(part) * 60 ** index for index, part in enumerate(reversed(parts)))
        rows = []
        for match in re.finditer(r"([\d:.]+)\s+-->\s+([\d:.]+)[^\n]*\n(.*?)(?=\n\s*\n|$)", text, re.S):
            rows.append({"start": seconds(match[1]), "end": seconds(match[2]), "text": re.sub(r"<[^>]+>", "", match[3]).strip()})
        return (validate_transcript(rows, duration), duration) if rows else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def media_info(path):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        duration = float(info["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0 or duration > getattr(settings, "LABTWIN_MEDIA_MAX_SECONDS", 7200):
            raise LearningError("The lecture must be between 1 second and the configured duration limit.")
        if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
            raise LearningError("This lecture has no audio track. Upload timestamped captions alongside it.")
        return duration
    except FileNotFoundError as exc:
        raise LearningError("Media processing requires ffmpeg and ffprobe on the server.") from exc
    except (subprocess.SubprocessError, KeyError, ValueError) as exc:
        raise LearningError("The media file is corrupted or has an unsupported codec.") from exc


def validate_transcript(rows, duration):
    if not isinstance(rows, list) or not rows or len(rows) > 20000:
        raise LearningError("Captions must contain timestamped transcript segments.")
    output = []
    for row in rows:
        start, end = float(row["start"]), float(row["end"])
        text = str(row["text"]).strip()
        if not text or len(text) > 20000 or not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration + 1:
            raise LearningError("A transcript segment has invalid text or timestamps.")
        output.append({"start": start, "end": min(end, duration), "text": text})
    return sorted(output, key=lambda row: row["start"])


def transcribe(path):
    duration = media_info(path)
    if not os.environ.get("GROQ_API_KEY") or getattr(settings, "LABTWIN_DISABLE_REMOTE_AI", False):
        raise LearningError("Automatic transcription needs GROQ_API_KEY. Add timestamped captions or configure the key and retry.")
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=120, max_retries=1)
    rows = []
    with tempfile.TemporaryDirectory(prefix="labtwin-audio-") as directory:
        # Segments stay below provider attachment limits, with original offsets.
        for index, offset in enumerate(range(0, math.ceil(duration), 900)):
            audio = Path(directory) / f"segment-{index}.mp3"
            try:
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(offset), "-i", str(path), "-t", "900", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio)], capture_output=True, timeout=180, check=True)
                with audio.open("rb") as stream:
                    result = client.audio.transcriptions.create(file=(audio.name, stream), model=getattr(settings, "LABTWIN_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"), response_format="verbose_json", timestamp_granularities=["segment"])
                data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                for segment in data.get("segments", []):
                    rows.append({"start": offset + float(segment["start"]), "end": min(duration, offset + float(segment["end"])), "text": segment["text"]})
            except Exception as exc:
                raise LearningError("Speech transcription could not finish. The upload is retained; retry later or add captions.") from exc
    return validate_transcript(rows, duration), duration
