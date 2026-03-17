"""
Multilingual Voice Support
Auto-detects language and routes to appropriate STT/TTS pipeline.
Whisper supports 99+ languages natively.
TTS: Kokoro (English), Piper (multilingual), Google TTS fallback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Language → Kokoro/Piper voice mappings
LANGUAGE_VOICES = {
    "en": {"kokoro": "af_sky",     "piper": "en_US-amy-medium"},
    "fr": {"kokoro": None,          "piper": "fr_FR-siwis-medium"},
    "de": {"kokoro": None,          "piper": "de_DE-thorsten-medium"},
    "es": {"kokoro": None,          "piper": "es_ES-mls_9972-low"},
    "it": {"kokoro": None,          "piper": "it_IT-riccardo-x_low"},
    "pt": {"kokoro": None,          "piper": "pt_BR-faber-medium"},
    "ja": {"kokoro": "jf_alpha",    "piper": None},
    "zh": {"kokoro": "zf_xiaobei", "piper": None},
    "ko": {"kokoro": None,          "piper": None},
    "ru": {"kokoro": None,          "piper": "ru_RU-irinia-medium"},
    "ar": {"kokoro": None,          "piper": None},
    "hi": {"kokoro": None,          "piper": None},
    "nl": {"kokoro": None,          "piper": "nl_NL-rdh-medium"},
    "pl": {"kokoro": None,          "piper": "pl_PL-darkman-medium"},
    "sv": {"kokoro": None,          "piper": "sv_SE-nst-medium"},
}

# Whisper language code map (ISO 639-1)
WHISPER_LANGUAGES = {
    "en", "fr", "de", "es", "it", "pt", "ja", "zh", "ko", "ru",
    "ar", "hi", "nl", "pl", "sv", "tr", "uk", "vi", "th", "he",
    "el", "cs", "ro", "hu", "fi", "da", "no", "sk", "bg", "hr",
}


@dataclass
class LanguageConfig:
    code: str = "en"          # ISO 639-1
    name: str = "English"
    auto_detect: bool = True
    tts_engine: str = "kokoro"
    tts_voice: str = "af_sky"
    whisper_language: str | None = None   # None = auto-detect
    rtl: bool = False         # right-to-left script


class MultilingualManager:
    """
    Manages language detection, routing, and configuration.
    Integrates with VoicePipeline for transparent multilingual support.
    """

    def __init__(self) -> None:
        self._current_lang: str = "en"
        self._auto_detect: bool = True
        self._detector = None
        self._whisper = None

    async def load(self, whisper_model: Any = None) -> None:
        self._whisper = whisper_model
        try:
            from langdetect import DetectorFactory
            DetectorFactory.seed = 0
            logger.info("langdetect loaded for language detection")
        except ImportError:
            logger.info("langdetect not installed — using Whisper for language detection")

    # ─── Language detection ──────────────────────────────────────────────────

    def detect_from_text(self, text: str) -> str:
        """Detect language from transcribed text."""
        try:
            from langdetect import detect
            code = detect(text)
            return code if code in WHISPER_LANGUAGES else "en"
        except Exception:
            return "en"

    async def detect_from_audio(self, audio_path: str) -> str:
        """
        Use Whisper's built-in language detection from audio.
        Returns ISO 639-1 code.
        """
        if not self._whisper:
            return "en"
        try:
            loop = asyncio.get_event_loop()
            lang = await loop.run_in_executor(
                None,
                self._whisper_detect_lang,
                audio_path,
            )
            return lang
        except Exception:
            return "en"

    def _whisper_detect_lang(self, audio_path: str) -> str:
        """Run Whisper language detection synchronously."""
        segments, info = self._whisper.transcribe(
            audio_path,
            beam_size=1,
            language=None,  # auto-detect
            task="transcribe",
            vad_filter=True,
            without_timestamps=True,
        )
        lang = info.language if hasattr(info, "language") else "en"
        return lang if lang in WHISPER_LANGUAGES else "en"

    # ─── Config resolution ───────────────────────────────────────────────────

    def get_config(self, lang_code: str) -> LanguageConfig:
        """Get voice/STT config for a language code."""
        voices = LANGUAGE_VOICES.get(lang_code, LANGUAGE_VOICES["en"])

        # Choose best available TTS
        if voices.get("kokoro"):
            tts_engine = "kokoro"
            tts_voice  = voices["kokoro"]
        elif voices.get("piper"):
            tts_engine = "piper"
            tts_voice  = voices["piper"]
        else:
            tts_engine = "gtts"   # Google TTS fallback for unsupported languages
            tts_voice  = lang_code

        return LanguageConfig(
            code=lang_code,
            name=self._lang_name(lang_code),
            tts_engine=tts_engine,
            tts_voice=tts_voice,
            whisper_language=lang_code if lang_code in WHISPER_LANGUAGES else None,
            rtl=lang_code in {"ar", "he", "fa", "ur"},
        )

    def _lang_name(self, code: str) -> str:
        names = {
            "en": "English", "fr": "French", "de": "German", "es": "Spanish",
            "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "zh": "Chinese",
            "ko": "Korean", "ru": "Russian", "ar": "Arabic", "hi": "Hindi",
            "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "tr": "Turkish",
        }
        return names.get(code, code.upper())

    @property
    def current_language(self) -> str:
        return self._current_lang

    def set_language(self, code: str) -> LanguageConfig:
        self._current_lang = code
        return self.get_config(code)

    def list_supported(self) -> list[dict]:
        return [
            {
                "code": code,
                "name": self._lang_name(code),
                "tts": bool(v.get("kokoro") or v.get("piper")),
                "stt": code in WHISPER_LANGUAGES,
            }
            for code, v in LANGUAGE_VOICES.items()
        ]


# ─── Google TTS fallback (no local model needed) ─────────────────────────────

async def gtts_synthesize(text: str, lang: str = "en") -> bytes:
    """Synthesize speech using gTTS (requires internet)."""
    try:
        from gtts import gTTS
        import io
        loop = asyncio.get_event_loop()

        def _synth():
            tts = gTTS(text=text, lang=lang, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()

        return await loop.run_in_executor(None, _synth)
    except ImportError:
        logger.warning("gTTS not installed — cannot synthesize %s", lang)
        return b""
    except Exception as e:
        logger.error("gTTS synthesis error: %s", e)
        return b""
