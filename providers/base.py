"""
Interfaces abstractas. Cada proveedor nuevo implementa una de estas
clases y se registra en router.py — nunca se toca la lógica de
orquestación para agregar un proveedor nuevo.
"""
from abc import ABC, abstractmethod


class LlmProvider(ABC):
    name: str

    @abstractmethod
    async def chat(self, messages: list[dict], json_mode: bool = False) -> tuple[str, int, int]:
        """Devuelve (texto_respuesta, tokens_entrada, tokens_salida)."""
        ...


class TtsProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str, lang: str) -> bytes:
        """Devuelve audio en bytes (mp3)."""
        ...


class SttProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, lang: str) -> str:
        ...


class TranslationProvider(ABC):
    name: str

    @abstractmethod
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Devuelve el texto traducido. Lanza excepción si falla."""
        ...


class TranslationProvider(ABC):
    name: str

    @abstractmethod
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Devuelve el texto traducido. Lanza excepción si falla."""
        ...
