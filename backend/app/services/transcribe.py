"""Расшифровка голосовых: локально (faster-whisper) или через OpenAI Whisper API."""
import asyncio
import io
import os
import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)
_model = None


def _local_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        log.info("Загружаю модель Whisper %s…", settings.whisper_model)
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8",
                              download_root="/data/whisper" if os.access("/data", os.W_OK) else None)
    return _model


def _transcribe_local(data: bytes) -> str:
    segments, _ = _local_model().transcribe(io.BytesIO(data), language="ru", vad_filter=True, beam_size=5)
    return " ".join(s.text.strip() for s in segments).strip()


async def _transcribe_openai(data: bytes, filename: str) -> str:
    async with httpx.AsyncClient(timeout=120) as http:
        r = await http.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={"model": "whisper-1", "language": "ru"},
            files={"file": (filename, data)},
        )
        r.raise_for_status()
        return r.json()["text"].strip()


async def transcribe(data: bytes, filename: str = "voice.ogg") -> str:
    if settings.transcribe_provider == "openai":
        return await _transcribe_openai(data, filename)
    return await asyncio.to_thread(_transcribe_local, data)
