"""
Reflexion Loop para MermaOps — Chuwi aprende de cada interacción compleja.

Patrón Reflexion (Shinn et al., 2023): el agente reflexiona verbalmente sobre
pasadas interacciones y persiste lecciones cortas que informan futuras respuestas.
Sin reentrenamiento — las lecciones se inyectan en el system prompt.

Almacenamiento: tabla agent_memory (store_id, pattern_key, pattern_value).
Buffer rotante de 5 slots → máximo 5 lecciones activas por tienda.
"""
from __future__ import annotations
import asyncio
import logging

log = logging.getLogger("mermaops.reflexion")

_N_SLOTS = 5
_KEY_FMT  = "chuwi_reflexion_{:02d}"
_PTR_KEY  = "chuwi_reflexion_ptr"


def _slot_key(i: int) -> str:
    return _KEY_FMT.format(i % _N_SLOTS)


# ── Carga ─────────────────────────────────────────────────────────────────────

def load_reflexions(store_id: str) -> list[str]:
    """Carga las lecciones guardadas desde agent_memory. Devuelve lista vacía si falla."""
    from backend.core import database
    try:
        lessons: list[str] = []
        for i in range(_N_SLOTS):
            val = database.get_memory(store_id, _slot_key(i))
            if val:
                lessons.append(val)
        return lessons
    except Exception:
        return []


def get_reflexion_context(store_id: str) -> str:
    """Formatea las lecciones como bloque de contexto para el system prompt de Chuwi."""
    lessons = load_reflexions(store_id)
    if not lessons:
        return ""
    block = "\n".join(f"- {l}" for l in lessons)
    return f"\n\nLECCIONES APRENDIDAS (de interacciones previas):\n{block}"


# ── Guardado ──────────────────────────────────────────────────────────────────

def save_reflexion(store_id: str, lesson: str) -> None:
    """
    Persiste la lección en el siguiente slot del buffer rotante (FIFO, 5 slots).
    Trunca a 200 chars para evitar context bloat.
    """
    from backend.core import database
    try:
        ptr_str = database.get_memory(store_id, _PTR_KEY) or "0"
        ptr = int(ptr_str) % _N_SLOTS
        database.set_memory(store_id, _slot_key(ptr), lesson.strip()[:200])
        database.set_memory(store_id, _PTR_KEY, str((ptr + 1) % _N_SLOTS))
        log.debug("Reflexion slot %d guardada: %s", ptr, lesson[:60])
    except Exception as e:
        log.debug("save_reflexion falló: %s", e)


# ── Generación async ──────────────────────────────────────────────────────────

async def async_generate_and_save(
    store_id: str,
    query: str,
    response: str,
) -> None:
    """
    Genera una lección con Haiku y la persiste asíncronamente.
    Fire-and-forget — usar con asyncio.ensure_future().
    Solo llama al LLM si la query o respuesta son suficientemente sustanciales.
    """
    if len(query) + len(response) < 80:
        return
    from backend.core import llm
    try:
        loop = asyncio.get_running_loop()
        prompt = (
            "Eres asistente de un supermercado. Extrae UNA lección operativa "
            "concreta (<25 palabras) de este intercambio para mejorar futuras respuestas. "
            "Enfócate en patrones de la tienda, no en el formato de la respuesta.\n\n"
            f"Pregunta del encargado: {query[:300]}\n"
            f"Respuesta de Chuwi: {response[:500]}\n\n"
            "Lección (una frase):"
        )
        lesson: str = await loop.run_in_executor(
            None,
            lambda: llm.call_fast(prompt, max_tokens=60),
        )
        if lesson and len(lesson.strip()) > 10:
            save_reflexion(store_id, lesson.strip())
    except Exception as e:
        log.debug("async_generate_and_save falló: %s", e)
