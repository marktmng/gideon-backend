"""
Windows Native Speech Recognition Bridge for Gideon.
Provides offline, local-first speech-to-text using Windows System.Speech.Recognition
and ffmpeg for audio transcoding.
"""

import os
import shutil
import subprocess
import tempfile
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


def find_ffmpeg() -> Optional[str]:
    """Find ffmpeg binary on Windows."""
    path = shutil.which("ffmpeg")
    if path and os.path.exists(path):
        return path
    
    # Check standard winget paths
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(winget_base):
        for root, _, files in os.walk(winget_base):
            if "ffmpeg.exe" in files:
                candidate = os.path.join(root, "ffmpeg.exe")
                if os.path.isfile(candidate):
                    return candidate
    return None


def convert_to_wav(audio_bytes: bytes, source_ext: str = "webm") -> Optional[str]:
    """Convert audio bytes to a 16kHz 16-bit mono WAV file for SAPI recognition."""
    ffmpeg_path = find_ffmpeg() or "ffmpeg"
    
    with tempfile.NamedTemporaryFile(suffix=f".{source_ext}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = in_file.name

    out_path = in_path + ".wav"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i", in_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        out_path
    ]

    try:
        no_win = 0x08000000 if sys.platform == "win32" else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            creationflags=no_win,
        )
        if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 44:
            return out_path
        else:
            logger.warning("ffmpeg conversion failed: %s", proc.stderr.decode("utf-8", errors="replace")[:200])
            return None
    except Exception as exc:
        logger.warning("Error running ffmpeg: %s", exc)
        return None
    finally:
        try:
            if os.path.exists(in_path):
                os.remove(in_path)
        except Exception:
            pass


def transcribe_wav_sapi(wav_path: str) -> Optional[str]:
    """
    Transcribe a 16kHz mono WAV file using Windows native System.Speech.Recognition.
    Runs completely offline on Windows without any external API or cloud dependency.
    """
    if not os.path.exists(wav_path):
        return None

    ps_script = f"""
Add-Type -AssemblyName System.Speech
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$engine.LoadGrammar($grammar)
$engine.SetInputToWaveFile('{wav_path.replace("'", "''")}')
$res = $engine.Recognize([TimeSpan]::FromSeconds(6))
if ($res) {{
    Write-Output $res.Text
}}
$engine.Dispose()
"""
    try:
        no_win = 0x08000000 if sys.platform == "win32" else 0
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            text=True,
            creationflags=no_win,
        )
        if proc.returncode == 0:
            text = proc.stdout.strip()
            if text:
                return text
        return None
    except Exception as exc:
        logger.warning("SAPI recognition error: %s", exc)
        return None
    finally:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except Exception:
            pass

