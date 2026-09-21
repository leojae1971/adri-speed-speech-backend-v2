"""
Tabla de precios verificados de proveedores TTS/STT/Traducción/LLM.

Los precios son de septiembre de 2026. Verificar trimestralmente
contra la documentación oficial de cada proveedor.

Fuentes:
- Azure: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/
- Google: https://cloud.google.com/text-to-speech/pricing
- Sarvam: https://www.sarvam.ai/pricing
- Alibaba: https://www.alibabacloud.com/help/en/model-studio/
- Baidu: https://cloud.baidu.com/product/speech/tts
- Tencent: https://cloud.tencent.com/product/tts
- Langbly: https://langbly.com/pricing
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PriceInfo:
    service: str
    provider: str
    usd_per_million: Optional[float] = None       # TTS/translation/LLM input
    usd_per_million_out: Optional[float] = None   # LLM output
    usd_per_unit: Optional[float] = None          # STT (por minuto)
    license_commercial_ok: bool = True            # ¿Permite uso comercial?
    notes: str = ""


PRICES: dict[tuple[str, str], PriceInfo] = {
    # ══════════════════════════════════════════════════════════
    # TTS (por millón de caracteres)
    # ══════════════════════════════════════════════════════════
    ('tts', 'azure_standard'): PriceInfo(
        'tts', 'azure_standard', usd_per_million=15.0,
        license_commercial_ok=False,
        notes='Azure Neural Standard. Tier F0 NO permite comercial.'
    ),
    ('tts', 'azure_neural'): PriceInfo(
        'tts', 'azure_neural', usd_per_million=16.0,
        license_commercial_ok=False,
        notes='Azure Neural. Tier F0 NO permite comercial.'
    ),
    ('tts', 'azure_neural_hd'): PriceInfo(
        'tts', 'azure_neural_hd', usd_per_million=22.0,
        license_commercial_ok=False,
        notes='Azure Neural HD. Requiere tier S0.'
    ),
    ('tts', 'google_neural2'): PriceInfo(
        'tts', 'google_neural2', usd_per_million=16.0,
        license_commercial_ok=True,
        notes='Google Neural2. Requiere billing habilitado.'
    ),
    ('tts', 'google_standard'): PriceInfo(
        'tts', 'google_standard', usd_per_million=4.0,
        license_commercial_ok=True,
        notes='Google Standard.'
    ),
    ('tts', 'kokoro'): PriceInfo(
        'tts', 'kokoro', usd_per_million=0.0,
        license_commercial_ok=True,
        notes='Kokoro-82M Apache 2.0. Self-hosted. Coste real = GPU.'
    ),
    ('tts', 'sarvam'): PriceInfo(
        'tts', 'sarvam', usd_per_million=36.0,
        license_commercial_ok=True,
        notes='Sarvam Bulbul v3 (₹30/10K chars). 22 idiomas indios.'
    ),
    ('tts', 'alibaba_qwen'): PriceInfo(
        'tts', 'alibaba_qwen', usd_per_million=11.5,
        license_commercial_ok=True,
        notes='Qwen3-TTS-Flash ($0.115/10K chars).'
    ),
    ('tts', 'baidu'): PriceInfo(
        'tts', 'baidu', usd_per_million=7.0,
        license_commercial_ok=True,
        notes='Baidu TTS (0.5元/万 chars). Solo chino + dialectos.'
    ),
    ('tts', 'tencent_standard'): PriceInfo(
        'tts', 'tencent_standard', usd_per_million=12.5,
        license_commercial_ok=True,
        notes='Tencent TTS standard ($0.125/10K chars).'
    ),
    ('tts', 'edge'): PriceInfo(
        'tts', 'edge', usd_per_million=0.0,
        license_commercial_ok=False,
        notes='Edge TTS zona gris. NO usar en comercial.'
    ),

    # ══════════════════════════════════════════════════════════
    # Traducción (por millón de caracteres)
    # ══════════════════════════════════════════════════════════
    ('translation', 'langbly'): PriceInfo(
        'translation', 'langbly', usd_per_million=5.0,
        license_commercial_ok=True,
        notes='Langbly ($5/M).'
    ),
    ('translation', 'google'): PriceInfo(
        'translation', 'google', usd_per_million=20.0,
        license_commercial_ok=True,
        notes='Google NMT ($20/M después de 500K gratis).'
    ),
    ('translation', 'azure'): PriceInfo(
        'translation', 'azure', usd_per_million=10.0,
        license_commercial_ok=True,
        notes='Azure Translator.'
    ),
    ('translation', 'deepl'): PriceInfo(
        'translation', 'deepl', usd_per_million=25.0,
        license_commercial_ok=True,
        notes='DeepL (solo ~32 idiomas).'
    ),
    ('translation', 'sarvam'): PriceInfo(
        'translation', 'sarvam', usd_per_million=24.0,
        license_commercial_ok=True,
        notes='Sarvam Mayura (₹20/10K chars).'
    ),

    # ══════════════════════════════════════════════════════════
    # STT (por minuto de audio)
    # ══════════════════════════════════════════════════════════
    ('stt', 'whisper_local'): PriceInfo(
        'stt', 'whisper_local', usd_per_unit=0.0,
        license_commercial_ok=True,
        notes='Whisper self-hosted.'
    ),
    ('stt', 'sarvam'): PriceInfo(
        'stt', 'sarvam', usd_per_unit=0.36,
        license_commercial_ok=True,
        notes='Sarvam Saaras (₹30/hora).'
    ),
    ('stt', 'azure'): PriceInfo(
        'stt', 'azure', usd_per_unit=1.0,
        license_commercial_ok=True,
        notes='Azure STT standard.'
    ),
    ('stt', 'audar'): PriceInfo(
        'stt', 'audar', usd_per_unit=0.0,
        license_commercial_ok=True,
        notes='Audar-ASR self-hosted. Licencia Open (Flash).'
    ),

    # ══════════════════════════════════════════════════════════
    # LLM (por millón de tokens)
    # ══════════════════════════════════════════════════════════
    ('llm', 'groq_llama_3_3_70b'): PriceInfo(
        'llm', 'groq_llama_3_3_70b',
        usd_per_million=0.59, usd_per_million_out=0.79,
        license_commercial_ok=True,
        notes='Groq Llama 3.3 70B.'
    ),
    ('llm', 'groq_compound'): PriceInfo(
        'llm', 'groq_compound',
        usd_per_million=0.59, usd_per_million_out=0.79,
        license_commercial_ok=True,
        notes='Groq compound.'
    ),
    ('llm', 'gemini_1_5_flash'): PriceInfo(
        'llm', 'gemini_1_5_flash',
        usd_per_million=0.075, usd_per_million_out=0.3,
        license_commercial_ok=True,
        notes='Gemini 1.5 Flash.'
    ),
    ('llm', 'cerebras'): PriceInfo(
        'llm', 'cerebras',
        usd_per_million=0.0, usd_per_million_out=0.0,
        license_commercial_ok=True,
        notes='Cerebras free tier.'
    ),
    ('llm', 'deepseek'): PriceInfo(
        'llm', 'deepseek',
        usd_per_million=0.14, usd_per_million_out=0.28,
        license_commercial_ok=True,
        notes='DeepSeek V3.'
    ),
}


def get_price(service: str, provider: str) -> Optional[PriceInfo]:
    """Devuelve la información de precio o None si no está registrado."""
    return PRICES.get((service, provider))


def list_providers(service: str) -> list[PriceInfo]:
    """Lista todos los proveedores conocidos de un servicio."""
    return [p for (s, _), p in PRICES.items() if s == service]