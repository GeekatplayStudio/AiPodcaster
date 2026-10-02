"""FFmpeg / FFprobe wrappers.

All invocations pass fixed argument lists (never ``shell=True``) and only ever
operate on paths that the storage layer created.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ..schemas import MediaInfo

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
MAGIC_PREFIXES: tuple[bytes, ...] = (b"RIFF", b"ID3", b"fLaC", b"OggS", b"\x1a\x45\xdf\xa3", b"FORM", b"\x30\x26\xb2\x75")
SILENCE_START = re.compile(r"silence_start: ([0-9.]+)")
SILENCE_END = re.compile(r"silence_end: ([0-9.]+)")


class AudioError(RuntimeError):
    """Raised when media cannot be read or processed."""


def _run(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, encoding="utf-8", errors="replace")
    except FileNotFoundError as error:
        raise AudioError("FFmpeg is not installed or not on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise AudioError("Media processing timed out") from error
    if result.returncode != 0:
        raise AudioError(f"FFmpeg failed: {result.stderr.strip()[-400:]}")
    return result


def tools_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def looks_like_media(path: Path) -> bool:
    """Cheap signature check before FFprobe. MP3 without ID3 and MP4 handled separately."""
    with path.open("rb") as handle:
        head = handle.read(16)
    if head.startswith(MAGIC_PREFIXES):
        return True
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:  # raw MPEG frame sync
        return True
    return head[4:8] == b"ftyp"  # MP4 / M4A / MOV


def probe(path: Path) -> MediaInfo:
    result = _run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=120)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AudioError("Could not read media metadata") from error
    audio = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if audio is None:
        raise AudioError("The file does not contain an audio stream")
    duration = float(data.get("format", {}).get("duration") or audio.get("duration") or 0)
    return MediaInfo(
        duration_ms=int(duration * 1000),
        sample_rate=int(audio.get("sample_rate") or 0),
        channels=int(audio.get("channels") or 0),
        codec=str(audio.get("codec_name") or ""),
        size_bytes=int(data.get("format", {}).get("size") or path.stat().st_size),
    )


def to_wav(source: Path, target: Path, sample_rate: int = 48_000) -> Path:
    """Canonicalise to mono 16-bit PCM so every later step is deterministic."""
    _run([FFMPEG, "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(target)])
    return target


def to_wav_16k(source: Path, target: Path) -> Path:
    _run([FFMPEG, "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)])
    return target


def detect_silences(path: Path, min_ms: int, noise_db: float = -35.0) -> list[tuple[int, int]]:
    args = [FFMPEG, "-v", "info", "-i", str(path), "-af", f"silencedetect=noise={noise_db}dB:d={min_ms / 1000:.3f}", "-f", "null", "-"]
    result = _run(args)
    starts = [int(float(value) * 1000) for value in SILENCE_START.findall(result.stderr)]
    ends = [int(float(value) * 1000) for value in SILENCE_END.findall(result.stderr)]
    return list(zip(starts, ends, strict=False))


def measure_loudness(path: Path, target_lufs: float = -16.0) -> dict[str, float | None]:
    args = [FFMPEG, "-v", "info", "-i", str(path), "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    result = _run(args)
    matches = re.findall(r"\{[^{}]*\}", result.stderr)
    if not matches:
        return {"input_i": None, "input_tp": None}
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError:
        return {"input_i": None, "input_tp": None}

    def value(key: str) -> float | None:
        try:
            number = float(data.get(key))
        except (TypeError, ValueError):
            return None
        return None if number in {float("inf"), float("-inf")} or number != number else number

    return {"input_i": value("input_i"), "input_tp": value("input_tp")}


def cut_segments(source: Path, target: Path, keep: list[tuple[int, int]]) -> Path:
    """Render only the ``keep`` ranges (ms) with short crossfades at joins."""
    if not keep:
        raise AudioError("Nothing left to render after edits")
    parts: list[str] = []
    labels: list[str] = []
    for index, (start, end) in enumerate(keep):
        parts.append(f"[0:a]atrim=start={start / 1000:.3f}:end={end / 1000:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.005,afade=t=out:st={max((end - start) / 1000 - 0.005, 0):.3f}:d=0.005[s{index}]")
        labels.append(f"[s{index}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
    _run([FFMPEG, "-y", "-v", "error", "-i", str(source), "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(target)])
    return target


def master(source: Path, target: Path, target_lufs: float = -16.0) -> Path:
    """Gentle podcast chain: high-pass, de-ess-ish band limit, compression, loudness normalisation."""
    chain = f"highpass=f=80,acompressor=threshold=-18dB:ratio=2.5:attack=10:release=120:makeup=2,loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    _run([FFMPEG, "-y", "-v", "error", "-i", str(source), "-af", chain, "-ar", "44100", "-c:a", "pcm_s16le", str(target)])
    return target


def export_mp3(source: Path, target: Path, bitrate: str = "128k", metadata: dict[str, str] | None = None) -> Path:
    args = [FFMPEG, "-y", "-v", "error", "-i", str(source), "-vn", "-c:a", "libmp3lame", "-b:a", bitrate, "-id3v2_version", "3"]
    for key, value in (metadata or {}).items():
        args += ["-metadata", f"{key}={value}"]
    args.append(str(target))
    _run(args)
    return target


def concat_files(sources: list[Path], target: Path) -> Path:
    args = [FFMPEG, "-y", "-v", "error"]
    for source in sources:
        args += ["-i", str(source)]
    graph = "".join(f"[{index}:a]" for index in range(len(sources))) + f"concat=n={len(sources)}:v=0:a=1[out]"
    args += ["-filter_complex", graph, "-map", "[out]", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(target)]
    _run(args)
    return target
