"""
Proveedores chinos de traducción: Tencent Cloud y Niutrans.

Ambos ofrecen niveles gratuitos generosos sin requerir tarjeta de crédito,
y tienen servidores en China — latencia óptima para usuarios asiáticos.

- Tencent: 5M chars/mes gratis. API: tmt.tencentcloudapi.com
- Niutrans: 200K chars/día (~6M/mes). API: api.niutrans.com
"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from config import settings
from providers.base import TranslationProvider


# ══════════════════════════════════════════════════════════════
# TENCENT CLOUD TRANSLATION
# ══════════════════════════════════════════════════════════════

class TencentTranslation(TranslationProvider):
    """
    Tencent Cloud Machine Translation (TMT).
    Endpoint: POST https://tmt.tencentcloudapi.com
    Auth: TC3-HMAC-SHA256 signature with SecretId/SecretKey.
    Free tier: 5M chars/month.
    """
    name = "tencent"

    def __init__(self):
        self.secret_id = settings.tencent_secret_id
        self.secret_key = settings.tencent_secret_key
        self.region = settings.tencent_region
        self.endpoint = "tmt.tencentcloudapi.com"
        self.service = "tmt"
        self.version = "2018-03-21"

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_id and self.secret_key)

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _build_authorization(self, payload: str) -> str:
        """Construye la cabecera Authorization según TC3-HMAC-SHA256."""
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        # 1. CanonicalRequest
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = (
            f"content-type:application/json; charset=utf-8\n"
            f"host:{self.endpoint}\n"
        )
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (
            f"{http_request_method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )

        # 2. StringToSign
        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(
            canonical_request.encode("utf-8")
        ).hexdigest()
        string_to_sign = (
            f"{algorithm}\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashed_canonical_request}"
        )

        # 3. Signature
        secret_date = self._sign(
            f"TC3{self.secret_key}".encode("utf-8"), date
        )
        secret_service = self._sign(secret_date, self.service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # 4. Authorization header
        return (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_configured:
            raise RuntimeError("Tencent: TENCENT_SECRET_ID/SECRET_KEY no configuradas")

        payload = json.dumps({
            "SourceText": text,
            "Source": source_lang,
            "Target": target_lang,
            "ProjectId": 0,
        })

        headers = {
            "Authorization": self._build_authorization(payload),
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.endpoint,
            "X-TC-Action": "TextTranslate",
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(int(time.time())),
            "X-TC-Region": self.region,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://{self.endpoint}", content=payload, headers=headers
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Tencent HTTP {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()

        try:
            return data["Response"]["TargetText"]
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Tencent: respuesta inesperada: {data}") from e


# ══════════════════════════════════════════════════════════════
# NIUTRANS TRANSLATION
# ══════════════════════════════════════════════════════════════

class NiutransTranslation(TranslationProvider):
    """
    Niutrans (小牛翻译).
    Endpoint: POST https://api.niutrans.com/v2/text/translate
    Auth: API-KEY (simple header).
    Free tier: 200K chars/day (~6M/month).
    454 languages.
    """
    name = "niutrans"

    def __init__(self):
        self.api_key = settings.niutrans_api_key
        self.app_id = settings.niutrans_app_id
        self.endpoint = "https://api.niutrans.com/v2/text/translate"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _build_auth_str(self, timestamp: str) -> str:
        """
        authStr = MD5(appId + apiKey + timestamp), según documentación
        de Niutrans v2.
        """
        raw = f"{self.app_id}{self.api_key}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_configured:
            raise RuntimeError("Niutrans: NIUTRANS_API_KEY no configurada")

        timestamp = str(int(time.time() * 1000))  # milisegundos
        payload = {
            "from": source_lang,
            "to": target_lang,
            "appId": self.app_id,
            "srcText": text,
            "timestamp": timestamp,
            "authStr": self._build_auth_str(timestamp),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Niutrans HTTP {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()

        if data.get("errorCode"):
            raise RuntimeError(
                f"Niutrans error {data['errorCode']}: {data.get('errorMsg')}"
            )

        return data.get("tgtText", "")
