"""
Implementaciones concretas de LlmProvider.

Groq, Cerebras y DeepSeek exponen APIs compatibles con el formato de
OpenAI, así que reutilizamos el mismo cliente `openai` para las tres —
solo cambia base_url y api_key. Gemini usa su propio SDK.
"""
from openai import AsyncOpenAI
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
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat(
        self, messages: list[dict], json_mode: bool = False
    ) -> tuple[str, int, int]:
        """
        Si json_mode=True, se pide al proveedor que garantice JSON
        válido en la respuesta (soportado nativamente por Groq/
        Cerebras/DeepSeek vía response_format). Es la alternativa
        robusta a pedirle al LLM que use un delimitador de texto como
        '|' para separar idioma destino y traducción — un LLM puede
        "olvidar" el delimitador; con json_mode el proveedor fuerza
        JSON válido a nivel de API, no de buena voluntad del modelo.

        IMPORTANTE: si usas json_mode, tu prompt DEBE mencionar
        explícitamente "json" y el esquema esperado (ej. incluir un
        ejemplo de la forma {"target": "...", "translation": "..."}),
        o el proveedor puede rechazar la petición.
        """
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=300,  # limita el costo/tiempo de cada respuesta
            **kwargs,
        )
        text = resp.choices[0].message.content
        usage = resp.usage
        return text, usage.prompt_tokens, usage.completion_tokens


class GroqLlm(_OpenAICompatibleLlm):
    def __init__(self):
        super().__init__(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            model="llama-3.3-70b-versatile",
        )


class CerebrasLlm(_OpenAICompatibleLlm):
    def __init__(self):
        # OJO — verificado julio 2026: el catálogo público de Cerebras se
        # redujo drásticamente (reporte independiente, abril 2026). Solo
        # ~4 modelos siguen soportados oficialmente: llama3.1-8b,
        # gpt-oss-120b, qwen-3-235b-a22b-instruct-2507, zai-glm-4.7.
        # "llama-3.3-70b" (lo que había aquí antes) YA NO existe en el
        # catálogo y además tenía el formato de nombre equivocado (los
        # modelos de Cerebras no llevan guion entre "llama" y la versión:
        # es "llama3.1-8b", no "llama-3.1-8b"). Antes de desplegar,
        # confirma en https://inference-docs.cerebras.ai/models/overview
        # que este modelo sigue vigente — este proveedor cambia su
        # catálogo con más frecuencia que Groq o Gemini.
        super().__init__(
            name="cerebras",
            base_url="https://api.cerebras.ai/v1",
            api_key=settings.cerebras_api_key,
            model="gpt-oss-120b",
        )


class DeepSeekLlm(_OpenAICompatibleLlm):
    def __init__(self):
        # OJO: revisa la fecha de deprecación de alias de modelo en el
        # dashboard de DeepSeek antes de desplegar — cambian los nombres
        # de modelo con más frecuencia que otros proveedores.
        super().__init__(
            name="deepseek",
            base_url="https://api.deepseek.com",
            api_key=settings.deepseek_api_key,
            model="deepseek-chat",
        )


class GeminiFlashLlm(LlmProvider):
    def __init__(self):
        self.name = "gemini_flash"
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash")

    async def chat(
        self, messages: list[dict], json_mode: bool = False
    ) -> tuple[str, int, int]:
        # google-generativeai no tiene cliente async estable en todas las
        # versiones; para producción real, envuelve esto en un executor
        # (loop.run_in_executor) para no bloquear el event loop de FastAPI.
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        generation_config = {"response_mime_type": "application/json"} if json_mode else {}
        resp = self._model.generate_content(prompt, generation_config=generation_config)
        text = resp.text
        input_tokens = getattr(resp.usage_metadata, "prompt_token_count", len(prompt) // 4)
        output_tokens = getattr(resp.usage_metadata, "candidates_token_count", len(text) // 4)
        return text, input_tokens, output_tokens
