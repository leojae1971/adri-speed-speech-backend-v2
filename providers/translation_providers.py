"""
Implementaciones concretas de TranslationProvider:
- LangblyTranslation     → primario ($5/1M, free tier 500K/mes)
- GoogleCloudTranslation → fallback ($20/1M, free tier 500K/mes)
- AzureTranslation       → último recurso ($10/1M, free tier 2M/mes)

IMPORTANTE: el endpoint exacto de Langbly debe verificarse en
docs.langbly.com antes de producción. La estructura actual es
la más común de la industria (POST JSON con Authorization Bearer).
Ajusta _call_api si el formato real difiere.
"""
import json
from typing import Optional

import httpx

from config import settings
from providers.base import TranslationProvider
from utils_logger import Logger


class LangblyTranslation(TranslationProvider):
    """
    Langbly: API compatible con Google Translate v2.
    Endpoint: POST {base_url}/language/translate/v2
    Auth: header X-API-Key
    Docs: https://langbly.com/docs
    """
    name = "langbly"

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.langbly_base_url).rstrip("/")
        self.api_key = api_key or settings.langbly_api_key

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_configured:
            raise RuntimeError("Langbly: LANGBLY_API_KEY no configurada")

        url = f"{self.base_url}/language/translate/v2"
        payload = {
            "q": text,
            "target": target_lang,
            "source": source_lang,
            "format": "text",
        }
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Langbly HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()

        try:
            translation = data["data"]["translations"][0]["translatedText"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Langbly: respuesta inesperada: {data}") from e

        return translation
class GoogleCloudTranslation(TranslationProvider):
    name = "google_translate"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            # Import perezoso para no romper el arranque si no hay
            # credenciales de Google configuradas.
            from google.cloud import translate_v2 as translate
            self._client = translate.Client()
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(settings.google_tts_credentials_path)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_configured:
            raise RuntimeError("Google Translate: GOOGLE_APPLICATION_CREDENTIALS no configurada")
        client = self._get_client()
        # google-cloud-translate es síncrono; lo ejecutamos directo
        # (FastAPI acepta llamadas blocking en handlers async si son cortas)
        result = client.translate(
            text,
            source_language=source_lang,
            target_language=target_lang,
            format_="text",
        )
        return result["translatedText"]


class AzureTranslation(TranslationProvider):
    name = "azure_translator"

    def __init__(self):
        self.key = settings.azure_speech_key
        self.region = settings.azure_speech_region
        self.endpoint = "https://api.cognitive.microsofttranslator.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.key)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_configured:
            raise RuntimeError("Azure Translator: AZURE_SPEECH_KEY no configurada")
        url = f"{self.endpoint}/translate"
        params = {"api-version": "3.0", "from": source_lang, "to": target_lang}
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-Type": "application/json",
        }
        body = [{"text": text}]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, params=params, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Azure Translator HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()

        try:
            return data[0]["translations"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Azure Translator: respuesta inesperada: {data}") from e
