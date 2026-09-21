"""
Caché de traducciones por hash de (texto, origen, destino, proveedor, versión).

Paralelo a cache.py (que solo cachea audio TTS). Este módulo añade
la caché de traducción de texto, que es la de mayor retorno: en una
app educativa las mismas frases se traducen una y otra vez entre
usuarios y sesiones. Un hit de caché es $0 y <5 ms.

Uso:
    from translation_cache import get_cached_translation, store_translation
    
    cached = get_cached_translation(text, src, tgt, provider="langbly")
    if cached is None:
        result = await provider.translate(...)
        store_translation(text, src, tgt, result, provider="langbly")
"""
import hashlib
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings


CACHE_VERSION = "v1"  # bumpear si cambia la lógica de normalización


def _normalize(text: str) -> str:
    """Normaliza el texto para maximizar hits de caché."""
    return " ".join(text.lower().split())


def _cache_key(text: str, src: str, tgt: str, provider: str) -> str:
    raw = f"{_normalize(text)}|{src.lower()}|{tgt.lower()}|{provider}|{CACHE_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TranslationCache:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or getattr(settings, "translation_cache_db", "translation_cache.db")
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translation_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL UNIQUE,
                    source_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    cache_version TEXT NOT NULL DEFAULT 'v1',
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_hit_at TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_langpair "
                "ON translation_cache(source_lang, target_lang)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_provider "
                "ON translation_cache(provider)"
            )
            conn.commit()

    def get(self, text: str, src: str, tgt: str, provider: str) -> Optional[str]:
        """Devuelve la traducción cacheada o None si no existe."""
        key = _cache_key(text, src, tgt, provider)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT translation FROM translation_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
                if row:
                    now = datetime.utcnow().isoformat()
                    conn.execute(
                        "UPDATE translation_cache "
                        "SET hit_count = hit_count + 1, last_hit_at = ? "
                        "WHERE cache_key = ?",
                        (now, key),
                    )
                    conn.commit()
                    return row[0]
        return None

    def get_any_provider(self, text: str, src: str, tgt: str) -> Optional[tuple[str, str]]:
        """Busca la traducción en CUALQUIER proveedor (útil antes de llamar a APIs)."""
        norm = _normalize(text)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("""
                    SELECT translation, provider FROM translation_cache
                    WHERE source_lang = ? AND target_lang = ?
                      AND cache_version = ?
                      AND LOWER(TRIM(source_text)) = ?
                    LIMIT 1
                """, (src.lower(), tgt.lower(), CACHE_VERSION, norm)).fetchone()
                return (row[0], row[1]) if row else None

    def store(self, text: str, src: str, tgt: str, translation: str, provider: str) -> None:
        key = _cache_key(text, src, tgt, provider)
        now = datetime.utcnow().isoformat()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO translation_cache
                    (cache_key, source_text, source_lang, target_lang,
                     translation, provider, cache_version, hit_count,
                     created_at, last_hit_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, NULL)
                """, (key, text, src.lower(), tgt.lower(),
                      translation, provider, CACHE_VERSION, now))
                conn.commit()

    def stats(self) -> dict:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM translation_cache"
                ).fetchone()[0]
                total_hits = conn.execute(
                    "SELECT COALESCE(SUM(hit_count), 0) FROM translation_cache"
                ).fetchone()[0]
                by_lang = conn.execute("""
                    SELECT source_lang, target_lang, COUNT(*) AS n,
                           SUM(hit_count) AS hits
                    FROM translation_cache
                    GROUP BY source_lang, target_lang
                    ORDER BY n DESC
                    LIMIT 20
                """).fetchall()
                by_provider = conn.execute("""
                    SELECT provider, COUNT(*) AS n
                    FROM translation_cache
                    GROUP BY provider
                    ORDER BY n DESC
                """).fetchall()
        return {
            "total_entries": total,
            "total_hits": total_hits,
            "avg_hits_per_entry": round(total_hits / total, 2) if total else 0.0,
            "by_language_pair": [
                {"source": r[0], "target": r[1], "entries": r[2], "hits": r[3] or 0}
                for r in by_lang
            ],
            "by_provider": [
                {"provider": r[0], "entries": r[1]} for r in by_provider
            ],
        }


_cache_instance: Optional[TranslationCache] = None
_cache_lock = threading.Lock()


def get_translation_cache() -> TranslationCache:
    """Singleton thread-safe."""
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = TranslationCache()
    return _cache_instance
