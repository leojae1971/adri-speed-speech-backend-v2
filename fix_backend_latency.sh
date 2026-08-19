#!/usr/bin/env bash
# ============================================================
# ADRI SPEED SPEECH BACKEND — fix de latencia
# ============================================================
# Ejecutar desde la raíz del repo del backend (donde está
# providers/llm_providers.py):
#
#   chmod +x fix_backend_latency.sh
#   ./fix_backend_latency.sh
#
# Corrige 2 causas reales de la latencia enorme / "primera pregunta
# falla, segunda funciona":
#
#  1. AsyncOpenAI (Groq/Cerebras/DeepSeek) sin timeout explícito usa
#     el default de la librería (varios minutos). Si un proveedor se
#     cuelga sin dar error, route_chat() se queda esperando ahí en
#     vez de pasar rápido al siguiente proveedor de la cadena.
#
#  2. La llamada a Gemini (generate_content) es SÍNCRONA/BLOQUEANTE
#     dentro de una función async — congela el event loop ENTERO de
#     FastAPI mientras espera, afectando a TODAS las peticiones
#     concurrentes, no solo la que llamó a Gemini. El propio código
#     ya tenía un comentario admitiendo el riesgo, sin corregirlo.
#
# Después de correr esto: hay que RE-DESPLEGAR el backend en Render
# para que tome efecto (no basta con el commit local).
# ============================================================
set -euo pipefail

FILE="providers/llm_providers.py"
BACKUP_SUFFIX=".bak_$(date +%Y%m%d_%H%M%S)"
cp "$FILE" "$FILE$BACKUP_SUFFIX"

python3 - "$FILE" << 'PYEOF'
import sys
path = sys.argv[1]
s = open(path, encoding='utf-8').read()

# --- 1) timeout explícito para Groq/Cerebras/DeepSeek ---
old_imports = '''from openai import AsyncOpenAI
import google.generativeai as genai

from config import settings
from providers.base import LlmProvider


class _OpenAICompatibleLlm(LlmProvider):
    """Base reutilizable para Groq / Cerebras / DeepSeek."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)'''

new_imports = '''import asyncio
import httpx
from openai import AsyncOpenAI
import google.generativeai as genai

from config import settings
from providers.base import LlmProvider

# FIX latencia: AsyncOpenAI sin `timeout=` explícito usa el default de
# la librería (varios minutos). Si un proveedor se cuelga (no da
# error, simplemente no responde), route_chat() se queda esperando
# ahí mucho más de lo razonable ANTES de intentar el siguiente de la
# cadena. 12s da margen de sobra para una respuesta normal y falla
# rápido si el proveedor no contesta.
_PROVIDER_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)


class _OpenAICompatibleLlm(LlmProvider):
    """Base reutilizable para Groq / Cerebras / DeepSeek."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=_PROVIDER_TIMEOUT
        )'''

assert old_imports in s, "no se encontró el bloque inicial de _OpenAICompatibleLlm"
s = s.replace(old_imports, new_imports)

# --- 2) Gemini: run_in_executor para no bloquear el event loop ---
old_gemini = '''    async def chat(
        self, messages: list[dict], json_mode: bool = False
    ) -> tuple[str, int, int]:
        # google-generativeai no tiene cliente async estable en todas las
        # versiones; para producción real, envuelve esto en un executor
        # (loop.run_in_executor) para no bloquear el event loop de FastAPI.
        prompt = "\\n".join(f"{m['role']}: {m['content']}" for m in messages)
        generation_config = {"response_mime_type": "application/json"} if json_mode else {}
        resp = self._model.generate_content(prompt, generation_config=generation_config)
        text = resp.text'''

new_gemini = '''    async def chat(
        self, messages: list[dict], json_mode: bool = False
    ) -> tuple[str, int, int]:
        # FIX: generate_content() es SÍNCRONO/BLOQUEANTE. Llamarlo
        # directamente dentro de una función async congela el event
        # loop ENTERO de FastAPI mientras espera a Gemini — TODAS las
        # peticiones concurrentes quedan congeladas, no solo esta.
        # run_in_executor lo mueve a un thread aparte para no bloquear.
        prompt = "\\n".join(f"{m['role']}: {m['content']}" for m in messages)
        generation_config = {"response_mime_type": "application/json"} if json_mode else {}
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content(
                prompt, generation_config=generation_config
            ),
        )
        text = resp.text'''

assert old_gemini in s, "no se encontró el método chat() de GeminiFlashLlm"
s = s.replace(old_gemini, new_gemini)

open(path, 'w', encoding='utf-8').write(s)
print("providers/llm_providers.py: timeout agregado + Gemini ya no bloquea el event loop.")
PYEOF

echo ""
echo "============================================================"
echo " Listo. Backup: $FILE$BACKUP_SUFFIX"
echo " Siguiente paso: commitear y RE-DESPLEGAR en Render."
echo "============================================================"
