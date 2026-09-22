"""
Punto de entrada. Flutter SOLO conoce estos endpoints — nunca
Groq, Azure, Gemini, etc. directamente.
"""
import asyncio
import base64
import json
import os

_google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if _google_creds_json:
    _creds_path = "/tmp/google-credentials.json"
    with open(_creds_path, "w") as f:
        f.write(_google_creds_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _creds_path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from router import route_chat, route_tts, route_stt, AllProvidersExhausted, route_translation
from viseme import estimate_visemes
from startup_checks import validate_llm_catalogs

app = FastAPI(title="ADRI SPEED SPEECH Backend")


@app.on_event("startup")
async def _startup_model_validation():
    await validate_llm_catalogs([
        ("groq", route_chat.__self__ if hasattr(route_chat, '__self__') else None),
    ])


class ChatRequest(BaseModel):
    messages: list[dict]
    json_mode: bool = False
    voice_id: str = "en-GB-SoniaNeural"
    lang: str = "en-GB"


class TtsRequest(BaseModel):
    text: str
    voice_id: str = "en-US-AvaNeural"
    lang: str = "en-US"


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        # 1. Obtener respuesta del LLM
        result = await route_chat(req.messages, json_mode=req.json_mode)
        
        # 2. Generar audio INMEDIATAMENTE (no en background)
        text = result.get("text", "")
        audio_base64 = None
        visemes = []
        
        tts_provider_used = None
        if text:
            try:
                tts_result = await route_tts(text, req.voice_id, req.lang)
                audio_base64 = base64.b64encode(tts_result["audio"]).decode("ascii")
                visemes = estimate_visemes(text)
                tts_provider_used = tts_result.get("provider_used")
            except Exception as e:
                # Audio no es crítico, no fallamos el chat por esto
                pass

        # Instrumentación de coste (no bloquea si falla)
        try:
            from cost_meter import get_cost_meter, CostEvent
            tokens = result.get("tokens") or {}
            tokens_in = tokens.get("input") if isinstance(tokens, dict) else None
            tokens_out = tokens.get("output") if isinstance(tokens, dict) else None
            get_cost_meter().log(CostEvent(
                service='llm',
                provider=result.get('provider_used', 'unknown'),
                language=req.lang,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                endpoint='/chat',
            ))
            if audio_base64 and tts_provider_used:
                get_cost_meter().log(CostEvent(
                    service='tts',
                    provider=tts_provider_used,
                    language=req.lang,
                    characters=len(text),
                    endpoint='/chat-tts',
                ))
        except Exception:
            pass

        # 3. Devolver TODO junto: texto + audio + visemes
        response = {
            "text": text,
            "provider_used": result.get("provider_used"),
            "tokens": result.get("tokens"),
        }
        
        if audio_base64:
            response["audio_base64"] = audio_base64
            response["visemes"] = visemes
            
        if req.json_mode:
            try:
                response["parsed"] = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                response["parsed"] = None
                
        return response
        
    except AllProvidersExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/tts")
async def tts(req: TtsRequest):
    try:
        result = await route_tts(req.text, req.voice_id, req.lang)

        # Instrumentación de coste (no bloquea si falla)
        try:
            from cost_meter import get_cost_meter, CostEvent
            get_cost_meter().log(CostEvent(
                service='tts',
                provider=result.get('provider_used', 'unknown'),
                language=req.lang,
                characters=len(req.text),
                endpoint='/tts',
            ))
        except Exception:
            pass

        return {
            "audio_base64": base64.b64encode(result["audio"]).decode("ascii"),
            "provider_used": result["provider_used"],
            "visemes": estimate_visemes(req.text),
        }
    except AllProvidersExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str = Form("en")):
    try:
        audio_bytes = await file.read()
        return await route_stt(audio_bytes, lang)
    except AllProvidersExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}



# ═══════════════════════════════════════════════════════════
# COST METER — Endpoints admin (solo lectura, sin coste)
# ═══════════════════════════════════════════════════════════

@app.get("/admin/costs/summary")
async def admin_cost_summary(days: int = 30):
    """Resumen del coste de los últimos N días."""
    try:
        from cost_meter import get_cost_meter
        return get_cost_meter().get_summary(days=days)
    except Exception as e:
        return {"error": str(e), "hint": "Cost Meter no inicializado"}


@app.get("/admin/costs/by-language")
async def admin_cost_by_language(days: int = 30):
    """Coste desglosado por idioma."""
    try:
        from cost_meter import get_cost_meter
        return {"days": days, "breakdown": get_cost_meter().get_cost_by_language(days=days)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/admin/costs/by-provider")
async def admin_cost_by_provider(days: int = 30):
    """Coste desglosado por proveedor."""
    try:
        from cost_meter import get_cost_meter
        return {"days": days, "breakdown": get_cost_meter().get_cost_by_provider(days=days)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/admin/pricing")
async def admin_pricing():
    """Lista de precios verificados de todos los proveedores."""
    try:
        from pricing import list_providers
        result = {}
        for service in ('tts', 'translation', 'stt', 'llm'):
            result[service] = [
                {
                    'provider': p.provider,
                    'usd_per_million': p.usd_per_million,
                    'usd_per_million_out': p.usd_per_million_out,
                    'usd_per_unit': p.usd_per_unit,
                    'license_commercial_ok': p.license_commercial_ok,
                    'notes': p.notes,
                }
                for p in list_providers(service)
            ]
        return result
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# TRANSLATION — Caché + cadena de proveedores
# ═══════════════════════════════════════════════════════════

class TranslationRequest(BaseModel):
    text: str
    source: str
    target: str


@app.post("/translate")
async def translate(req: TranslationRequest, request: Request = None):
    """Traduce texto usando caché + cadena regional de proveedores."""
    try:
        # Detectar región del usuario
        region = "west"
        if request is not None:
            from router import detect_user_region
            region = detect_user_region(
                request_headers=dict(request.headers),
                accept_language=request.headers.get("accept-language"),
            )

        result = await route_translation(
            req.text, req.source, req.target, user_region=region
        )

        # Instrumentación de coste (no bloquea)
        try:
            from cost_meter import get_cost_meter, CostEvent
            get_cost_meter().log(CostEvent(
                service='translation',
                provider=result['provider_used'],
                language=req.target,
                characters=len(req.text),
                cache_hit=result['cache_hit'],
                endpoint='/translate',
            ))
        except Exception:
            pass

        return result
    except AllProvidersExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/admin/cache/stats")
async def admin_cache_stats():
    """Estadísticas de la caché de traducción."""
    try:
        from translation_cache import get_translation_cache
        return get_translation_cache().stats()
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# TRANSLATION — Caché + cadena de proveedores
# ═══════════════════════════════════════════════════════════

class TranslationRequest(BaseModel):
    text: str
    source: str
    target: str


@app.post("/translate")
async def translate(req: TranslationRequest):
    """Traduce texto usando caché + cadena Langbly → Google → Azure."""
    try:
        result = await route_translation(req.text, req.source, req.target)

        # Instrumentación de coste (no bloquea)
        try:
            from cost_meter import get_cost_meter, CostEvent
            get_cost_meter().log(CostEvent(
                service='translation',
                provider=result['provider_used'],
                language=req.target,
                characters=len(req.text),
                cache_hit=result['cache_hit'],
                endpoint='/translate',
            ))
        except Exception:
            pass

        return result
    except AllProvidersExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/admin/cache/stats")
async def admin_cache_stats():
    """Estadísticas de la caché de traducción."""
    try:
        from translation_cache import get_translation_cache
        return get_translation_cache().stats()
    except Exception as e:
        return {"error": str(e)}

