"""
Cost Meter — registra cada llamada a TTS/STT/traducción/LLM con
precios verificados. Almacena en SQLite local (sin dependencias
externas). Migrable a PostgreSQL en producción.

Uso:
    from cost_meter import get_cost_meter, CostEvent
    
    meter = get_cost_meter()
    meter.log(CostEvent(
        service='tts',
        provider='sarvam',
        language='hi',
        characters=len(text),
        latency_ms=250,
    ))
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
from contextlib import contextmanager
import sqlite3
import json
import os
import threading

from pricing import get_price


@dataclass
class CostEvent:
    service: str                              # 'tts' | 'translation' | 'stt' | 'llm'
    provider: str
    language: Optional[str] = None
    characters: Optional[int] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    cache_hit: bool = False
    endpoint: Optional[str] = None
    user_hash: Optional[str] = None
    metadata: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class CostMeter:
    def __init__(self, db_path: str = "cost_events.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cost_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    language TEXT,
                    characters INTEGER,
                    tokens_in INTEGER,
                    tokens_out INTEGER,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    latency_ms INTEGER,
                    cache_hit INTEGER NOT NULL DEFAULT 0,
                    endpoint TEXT,
                    user_hash TEXT,
                    metadata_json TEXT
                )
            """)
            for idx in ('service', 'timestamp', 'language', 'provider'):
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{idx} "
                    f"ON cost_events({idx})"
                )
            conn.commit()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            yield conn
        finally:
            conn.close()

    def log(self, event: CostEvent) -> float:
        """Registra un evento. Devuelve el coste estimado en USD."""
        cost_usd = 0.0 if event.cache_hit else self._estimate_cost(event)

        with self._lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO cost_events
                    (timestamp, service, provider, language, characters,
                     tokens_in, tokens_out, cost_usd, latency_ms,
                     cache_hit, endpoint, user_hash, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.timestamp.isoformat(),
                    event.service,
                    event.provider,
                    event.language,
                    event.characters,
                    event.tokens_in,
                    event.tokens_out,
                    cost_usd,
                    event.latency_ms,
                    1 if event.cache_hit else 0,
                    event.endpoint,
                    event.user_hash,
                    json.dumps(event.metadata) if event.metadata else None,
                ))
                conn.commit()
        return cost_usd

    def _estimate_cost(self, event: CostEvent) -> float:
        price = get_price(event.service, event.provider)
        if price is None:
            return 0.0

        if event.service in ('tts', 'translation'):
            chars = event.characters or 0
            return (chars / 1_000_000) * (price.usd_per_million or 0.0)

        if event.service == 'llm':
            in_cost = ((event.tokens_in or 0) / 1_000_000) * (price.usd_per_million or 0.0)
            out_cost = ((event.tokens_out or 0) / 1_000_000) * (price.usd_per_million_out or 0.0)
            return in_cost + out_cost

        if event.service == 'stt':
            minutes = (event.metadata or {}).get('minutes', 1.0)
            return minutes * (price.usd_per_unit or 0.0)

        return 0.0

    # ══════════════════════════════════════════════════════════
    # CONSULTAS
    # ══════════════════════════════════════════════════════════
    def get_daily_cost(self, day: Optional[date] = None) -> float:
        if day is None:
            day = date.today()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM cost_events
                WHERE date(timestamp) = ?
            """, (day.isoformat(),)).fetchone()
        return row[0] if row else 0.0

    def get_cost_by_language(self, days: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT language,
                       COALESCE(SUM(cost_usd), 0) as cost,
                       COUNT(*) as events,
                       SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as hits
                FROM cost_events
                WHERE timestamp >= datetime('now', ?)
                GROUP BY language
                ORDER BY cost DESC
            """, (f'-{days} days',)).fetchall()
        return [
            {
                'language': r[0],
                'cost_usd': r[1],
                'events': r[2],
                'cache_hits': r[3] or 0,
                'cache_hit_rate': (r[3] or 0) / r[2] if r[2] else 0.0,
            }
            for r in rows
        ]

    def get_cost_by_provider(self, days: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT service, provider,
                       COALESCE(SUM(cost_usd), 0) as cost,
                       COUNT(*) as events,
                       AVG(latency_ms) as avg_latency
                FROM cost_events
                WHERE timestamp >= datetime('now', ?)
                GROUP BY service, provider
                ORDER BY cost DESC
            """, (f'-{days} days',)).fetchall()
        return [
            {
                'service': r[0],
                'provider': r[1],
                'cost_usd': r[2],
                'events': r[3],
                'avg_latency_ms': r[4],
            }
            for r in rows
        ]

    def get_summary(self, days: int = 30) -> dict:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(cost_usd), 0),
                       COUNT(*),
                       SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END)
                FROM cost_events
                WHERE timestamp >= datetime('now', ?)
            """, (f'-{days} days',)).fetchone()
        total_cost = row[0] or 0.0
        total_events = row[1] or 0
        cache_hits = row[2] or 0
        return {
            'period_days': days,
            'total_cost_usd': round(total_cost, 6),
            'total_events': total_events,
            'cache_hits': cache_hits,
            'cache_hit_rate': cache_hits / total_events if total_events else 0.0,
            'daily_avg_usd': round(total_cost / days, 6) if days else 0.0,
            'monthly_projection_usd': round((total_cost / days) * 30, 4) if days else 0.0,
        }


_meter: Optional[CostMeter] = None
_meter_lock = threading.Lock()


def get_cost_meter() -> CostMeter:
    """Singleton thread-safe."""
    global _meter
    if _meter is None:
        with _meter_lock:
            if _meter is None:
                db_path = os.getenv('COST_METER_DB', 'cost_events.db')
                _meter = CostMeter(db_path)
    return _meter