import os
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Límites verificados contra documentación oficial de cada proveedor
# (julio 2026). Estos números cambian sin aviso — revisa los dashboards
# de cada proveedor cada pocas semanas y ajusta SOLO aquí. Ningún otro
# archivo debería tener un número de cuota escrito directamente.
# ---------------------------------------------------------------------------


@dataclass
class ProviderLimits:
    name: str
    rpm: Optional[int] = None              # requests por minuto
    rpd: Optional[int] = None              # requests por día
    tpm: Optional[int] = None              # tokens por minuto
    tpd: Optional[int] = None              # tokens por día
    chars_per_month: Optional[int] = None  # solo TTS
    context_window: Optional[int] = None   # tokens máximos de entrada (solo LLM)
    reset: str = "daily"                   # "daily" | "monthly" | "none"
    unlimited: bool = False
    notes: str = ""


# Los contadores son GLOBALES (por cuenta), no por usuario. Esto es
# intencional: los free tiers de Groq/Cerebras/Azure limitan por CUENTA,
# no por usuario final. Con 5 usuarios compartiendo la app, la cuota se
# reparte entre todos — es exactamente como el proveedor lo ve.
LLM_PROVIDERS_CONFIG = {
    "groq": ProviderLimits(
        name="groq", rpm=30, rpd=1000, tpm=6000, context_window=8192, reset="daily",
        notes="Límite por modelo, no por cuenta completa. "
              "Usamos llama-3.3-70b-versatile como modelo por defecto. "
              "context_window=8192 es una ESTIMACIÓN CONSERVADORA, no "
              "verificada oficialmente — confírmalo en console.groq.com.",
    ),
    "cerebras": ProviderLimits(
        name="cerebras", rpm=5, tpd=1_000_000, tpm=30_000, context_window=8192, reset="daily",
        notes="RPM bajado de 30 a 5 en 2026 — verifica en tu dashboard "
              "antes de confiar en este número a largo plazo. "
              "context_window=8192 es una ESTIMACIÓN CONSERVADORA sin "
              "verificar oficialmente para gpt-oss-120b — el modelo puede "
              "soportar bastante más; es un valor prudente para no "
              "arriesgarnos a un 400 a mitad de conversación.",
    ),
    "gemini_flash": ProviderLimits(
        name="gemini_flash", rpm=15, rpd=1500, tpm=1_000_000, context_window=1_000_000, reset="daily",
        notes="El reset ocurre a medianoche hora del Pacífico (PT), "
              "no a medianoche de Tanzania. Ojo con el cálculo del día. "
              "Gemini Flash sí tiene 1M de contexto documentado oficialmente "
              "— este número es más confiable que el de Groq/Cerebras.",
    ),
    "deepseek": ProviderLimits(
        name="deepseek", unlimited=True, context_window=64_000, reset="none",
        notes="NO es free tier permanente: regalo de 5M tokens, 30 días. "
              "Tras eso, factura por token (muy barato). Lo tratamos como "
              "colchón 'ilimitado mientras pagues centavos', último eslabón.",
    ),
}

TTS_PROVIDERS_CONFIG = {
    "azure": ProviderLimits(
        name="azure", chars_per_month=500_000, reset="monthly",
        notes="Tier F0, voces neural. Nunca expira.",
    ),
    "google_wavenet": ProviderLimits(
        name="google_wavenet", chars_per_month=1_000_000, reset="monthly",
        notes="OJO: el free tier de 4M caracteres de Google es para voces "
              "Standard (robóticas). WaveNet/Neural2 (voz humana) es 1M. "
              "No mezclar los dos números — ya nos equivocamos una vez "
              "analizando otras propuestas de arquitectura por esto.",
    ),
    "edge_tts": ProviderLimits(
        name="edge_tts", unlimited=True, reset="none",
        notes="NO OFICIAL. Reverse-engineered del motor de voz de Edge. "
              "Puede romperse sin aviso si Microsoft cambia el mecanismo "
              "de autenticación interno. Úsalo como último respaldo, "
              "nunca como proveedor único de producción.",
    ),
}

STT_PROVIDERS_CONFIG = {
    "groq_whisper": ProviderLimits(
        name="groq_whisper", rpd=2000, reset="daily",
    ),
    "whisper_local": ProviderLimits(
        name="whisper_local", unlimited=True, reset="none",
        notes="faster-whisper corriendo en el mismo servidor. Requiere "
              "CPU/GPU disponible — puedes usar tu PC con Ollama ya montado.",
    ),
}


TRANSLATION_PROVIDERS_CONFIG = {
    "tencent": ProviderLimits(
        name="tencent", chars_per_month=5_000_000, reset="monthly",
        notes="腾讯云翻译. Free tier: 5M chars/mes. Requiere SecretId/SecretKey "
              "(registro con email, sin tarjeta). Servidores en China.",
    ),
    "niutrans": ProviderLimits(
        name="niutrans", chars_per_month=6_000_000, reset="daily",
        notes="小牛翻译. Free tier: 200K chars/día. Requiere API-KEY "
              "(registro con email, sin tarjeta). 454 idiomas.",
    ),
    "langbly": ProviderLimits(
        name="langbly", chars_per_month=500_000, reset="monthly",
        notes="Primario por precio ($5/1M vs Google $20/M y Azure $10/M). "
              "Free tier 500K chars/mes. Verificar endpoint exacto en "
              "docs.langbly.com antes de producción.",
    ),
    "google_translate": ProviderLimits(
        name="google_translate", chars_per_month=500_000, reset="monthly",
        notes="Fallback. $20/1M después de 500K gratis. Requiere billing.",
    ),
    "azure_translator": ProviderLimits(
        name="azure_translator", chars_per_month=2_000_000, reset="monthly",
        notes="Último recurso. 2M chars/mes en tier F0. $10/1M después.",
    ),
}


TRANSLATION_PROVIDERS_CONFIG = {
    "langbly": ProviderLimits(
        name="langbly", chars_per_month=500_000, reset="monthly",
        notes="Primario por precio ($5/1M vs Google $20/M y Azure $10/M). "
              "Free tier 500K chars/mes. Verificar endpoint exacto en "
              "docs.langbly.com antes de producción.",
    ),
    "google_translate": ProviderLimits(
        name="google_translate", chars_per_month=500_000, reset="monthly",
        notes="Fallback. $20/1M después de 500K gratis. Requiere billing.",
    ),
    "azure_translator": ProviderLimits(
        name="azure_translator", chars_per_month=2_000_000, reset="monthly",
        notes="Último recurso. 2M chars/mes en tier F0. $10/1M después.",
    ),
}


@dataclass
class Settings:
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    cerebras_api_key: str = field(default_factory=lambda: os.getenv("CEREBRAS_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    azure_speech_key: str = field(default_factory=lambda: os.getenv("AZURE_SPEECH_KEY", ""))
    azure_speech_region: str = field(default_factory=lambda: os.getenv("AZURE_SPEECH_REGION", "eastus"))
    google_tts_credentials_path: str = field(
        default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    )
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "adri_speech.db"))
    audio_cache_dir: str = field(default_factory=lambda: os.getenv("AUDIO_CACHE_DIR", "./audio_cache"))
    translation_cache_db: str = field(
        default_factory=lambda: os.getenv("TRANSLATION_CACHE_DB", "translation_cache.db")
    )
    langbly_api_key: str = field(default_factory=lambda: os.getenv("LANGBLY_API_KEY", ""))
    tencent_secret_id: str = field(default_factory=lambda: os.getenv("TENCENT_SECRET_ID", ""))
    tencent_secret_key: str = field(default_factory=lambda: os.getenv("TENCENT_SECRET_KEY", ""))
    tencent_region: str = field(default_factory=lambda: os.getenv("TENCENT_REGION", "ap-beijing"))
    niutrans_api_key: str = field(default_factory=lambda: os.getenv("NIUTRANS_API_KEY", ""))
    niutrans_app_id: str = field(default_factory=lambda: os.getenv("NIUTRANS_APP_ID", ""))
    langbly_base_url: str = field(
        default_factory=lambda: os.getenv("LANGBLY_BASE_URL", "https://api.langbly.com")
    )
    translation_cache_db: str = field(
        default_factory=lambda: os.getenv("TRANSLATION_CACHE_DB", "translation_cache.db")
    )
    langbly_api_key: str = field(default_factory=lambda: os.getenv("LANGBLY_API_KEY", ""))
    langbly_base_url: str = field(
        default_factory=lambda: os.getenv("LANGBLY_BASE_URL", "https://api.langbly.com")
    )


settings = Settings()
