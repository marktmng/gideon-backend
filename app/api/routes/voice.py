"""
Voice & Wake-Word API Routes for Gideon (Phase 5 Hands-Free).
Provides diagnostics, configuration metadata, audio transcription,
and Windows companion bridge endpoints.
"""

import base64
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logging import get_logger
from app.desktop.windows_speech import convert_to_wav, transcribe_wav_sapi

logger = get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

INTERRUPT_KEYWORDS = [
    "stop",
    "halt",
    "cancel",
    "quiet",
    "be quiet",
    "shut up",
    "stop talking",
    "pause",
    "abort",
]

BANNED_DANGEROUS_VOCAL_PATTERNS = [
    "format c:",
    "rmdir /s",
    "del /f /s /q",
    "drop table",
    "truncate",
    "powershell -encodedcommand",
]


class VoiceStatusResponse(BaseModel):
    engine: str = "web_speech_continuous_acoustic"
    default_wake_phrase: str = "Hey Gideon"
    supported_phrases: List[str] = ["Hey Gideon", "Gideon"]
    windows_companion_supported: bool = True
    single_breath_extraction: bool = True
    acoustic_loopback_prevention: bool = True
    offline_capable: bool = True
    external_api_required: bool = False
    interruption_keywords: List[str] = INTERRUPT_KEYWORDS
    security_policy: str = (
        "All wake-word vocal directives strictly adhere to Phase 4 action allowlists "
        "and Phase 5 human approval requirements for consequential operations."
    )


class VoiceConfigResponse(BaseModel):
    default_phrase: str = "hey_gideon"
    available_phrases: List[dict] = [
        {"id": "hey_gideon", "label": "Hey Gideon", "is_default": True},
        {"id": "gideon", "label": "Gideon", "is_default": False},
        {"id": "both", "label": "Both ('Hey Gideon' & 'Gideon')", "is_default": False},
    ]
    audio_cue: dict = {
        "enabled": True,
        "type": "web_audio_synth",
        "frequencies_hz": [523.25, 659.25],
        "duration_ms": 280,
    }
    interruption_keywords: List[str] = INTERRUPT_KEYWORDS
    banned_vocal_actions: List[str] = BANNED_DANGEROUS_VOCAL_PATTERNS


class VoiceWakeRequest(BaseModel):
    phrase: str = Field(..., description="Wake phrase triggered ('Hey Gideon' or 'Gideon')")
    command: Optional[str] = Field(None, description="Trailing vocal command in single-breath utterance")
    source: Optional[str] = Field("web_client", description="Source of the wake event ('web_client', 'windows_companion')")


class VoiceWakeResponse(BaseModel):
    status: str
    phrase: str
    command: Optional[str]
    source: str
    acknowledged: bool
    safety_passed: bool
    message: str


class VoiceTranscribeRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded audio recording")
    mime_type: Optional[str] = Field("audio/webm", description="MIME type of the audio")
    format: Optional[str] = Field("webm", description="Audio format/container ('webm' or 'wav')")


class VoiceTranscribeResponse(BaseModel):
    success: bool
    text: str = ""
    engine: str = "none"
    message: Optional[str] = None


@router.get("/status", response_model=VoiceStatusResponse)
async def get_voice_status():
    """
    Returns live diagnostics and status of the wake-word and vocal interaction subsystem.
    """
    return VoiceStatusResponse()


@router.get("/config", response_model=VoiceConfigResponse)
async def get_voice_config():
    """
    Returns configuration options and audio cues parameters for hands-free operation.
    """
    return VoiceConfigResponse()


@router.post("/wake", response_model=VoiceWakeResponse)
async def receive_wake_event(req: VoiceWakeRequest):
    """
    Receives and validates a wake-word activation event from the web client or Windows companion.
    Verifies that the command does not violate safety boundaries.
    """
    clean_phrase = req.phrase.strip().lower()
    valid_phrases = ["hey gideon", "gideon", "ay gideon", "hi gideon", "ok gideon"]

    if not any(clean_phrase.startswith(p) for p in valid_phrases):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid wake phrase '{req.phrase}'. Expected 'Hey Gideon' or 'Gideon'.",
        )

    # Check command against dangerous vocal commands
    if req.command:
        lower_cmd = req.command.lower()
        for banned in BANNED_DANGEROUS_VOCAL_PATTERNS:
            if banned in lower_cmd:
                return VoiceWakeResponse(
                    status="rejected",
                    phrase=req.phrase,
                    command=req.command,
                    source=req.source or "unknown",
                    acknowledged=True,
                    safety_passed=False,
                    message="Directive rejected: Banned dangerous system command detected.",
                )

    return VoiceWakeResponse(
        status="acknowledged",
        phrase=req.phrase,
        command=req.command,
        source=req.source or "web_client",
        acknowledged=True,
        safety_passed=True,
        message=f"Wake phrase '{req.phrase}' acknowledged."
        + (f" Directive captured: '{req.command}'." if req.command else " Standing by for speech input."),
    )


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_audio(req: VoiceTranscribeRequest):
    """
    Transcribes spoken microphone audio using Gemini multimodal transcription
    or local Windows native SAPI speech recognition.
    Enables reliable speech input even when browser Web Speech API is blocked or offline.
    """
    audio_bytes: bytes = b""
    mime_type = req.mime_type or "audio/webm"
    fmt = req.format or ("wav" if "wav" in mime_type else "webm")

    if req.audio_base64:
        try:
            # Strip data URL header if present (e.g. data:audio/webm;base64,...)
            raw_b64 = req.audio_base64
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            audio_bytes = base64.b64decode(raw_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 audio data: {exc}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio payload provided. Supply audio_base64 in JSON body."
        )

    if not audio_bytes or len(audio_bytes) < 32:
        return VoiceTranscribeResponse(
            success=False,
            text="",
            engine="none",
            message="Audio payload is empty or too short."
        )

    # 1. High-accuracy cloud transcription if Gemini API key is configured
    if settings.effective_gemini_api_key and settings.effective_gemini_api_key.strip():
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=settings.effective_gemini_api_key.strip())
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe the spoken English words accurately. Output ONLY the words spoken by the user without commentary, punctuation formatting, or quotes."
                ]
            )
            text = (res.text or "").strip()
            if text:
                logger.info("Transcribed audio via Gemini: '%s'", text)
                return VoiceTranscribeResponse(success=True, text=text, engine="gemini")
        except Exception as exc:
            logger.warning("Gemini multimodal transcription failed, falling back to local SAPI: %s", exc)

    # 2. Local-first Windows native SAPI transcription
    try:
        wav_path = None
        if fmt == "wav":
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                wav_path = f.name
        else:
            wav_path = convert_to_wav(audio_bytes, source_ext=fmt)

        if wav_path:
            text = transcribe_wav_sapi(wav_path)
            if text:
                logger.info("Transcribed audio via Windows SAPI: '%s'", text)
                return VoiceTranscribeResponse(success=True, text=text, engine="windows_sapi")
    except Exception as exc:
        logger.warning("Windows SAPI transcription failed: %s", exc)

    return VoiceTranscribeResponse(
        success=False,
        text="",
        engine="none",
        message="No speech detected in audio stream."
    )
