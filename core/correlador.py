"""Correlador de la espina — se enciende con ≥2 módulos vivos (desde Salud).

Cruza dominios (sueño ↔ ánimo ↔ gasto) VALIDANDO cada hipótesis contra el dato:
usa la MEDIANA (robusta a outliers), exige N suficiente por grupo, y ante la duda NO
afirma (guardia anti-patrones-falsos). Persiste solo los cruces que aguantan como
`inferencias` en Supabase, siempre con su dato — luego se validan con Nico (sí/no).

No es un módulo: orquesta lecturas de salud + finanzas (por su interfaz) y escribe a la
memoria (la espina cruza módulos). Idempotente: no re-propone lo ya creado/descartado.

Alineación de fechas: el sueño se reporta en el brief de la mañana del día D (= la noche
anterior) y el ánimo/gasto son del mismo día D → se cruzan en la MISMA fila del Diario.
"""
import logging
import statistics

from core import memory
from modules import finanzas, salud

logger = logging.getLogger(__name__)

# Guardias (canon: calla hasta tener datos; N chico → no afirma).
MIN_DIAS = 14       # ≥2 semanas con dato de sueño antes de intentar cualquier cruce
MIN_GRUPO = 4       # cada lado (buen/mal sueño) necesita este N para que la mediana valga
DELTA_ANIMO = 0.5   # caída de ánimo (escala 1-4) que tomamos como señal real
DELTA_GASTO = 0.25  # +25% de gasto mediano que tomamos como señal real


def _num_o_none(v):
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _dias_con_dato(diario: list[dict], gasto_por_dia: dict) -> list[dict]:
    """Normaliza el Diario + gasto a [{sueno_ok: bool|None, animo: float|None, gasto: float|None}]."""
    dias = []
    for f in diario:
        fecha = str(f.get("Fecha", "")).strip()
        sueno_raw = str(f.get(salud.COLS["sueno_7h"], "")).strip()
        dias.append({
            "fecha": fecha,
            "sueno_ok": salud._afirmativo(sueno_raw) if sueno_raw else None,
            "animo": _num_o_none(f.get(salud.COLS["animo"])),
            "gasto": gasto_por_dia.get(fecha),
        })
    return dias


def _analizar_sueno_animo(dias: list[dict]) -> str | None:
    mal = [d["animo"] for d in dias if d["sueno_ok"] is False and d["animo"] is not None]
    bien = [d["animo"] for d in dias if d["sueno_ok"] is True and d["animo"] is not None]
    if len(mal) < MIN_GRUPO or len(bien) < MIN_GRUPO:
        return None
    m_mal, m_bien = statistics.median(mal), statistics.median(bien)
    if m_bien - m_mal >= DELTA_ANIMO:
        return (f"Las noches que duermes menos de 7h, al otro día tu ánimo cae: mediana {m_mal:.1f}/4 "
                f"vs {m_bien:.1f}/4 cuando duermes bien (sobre {len(mal)} y {len(bien)} días).")
    return None


def _analizar_sueno_gasto(dias: list[dict]) -> str | None:
    mal = [d["gasto"] for d in dias if d["sueno_ok"] is False and d["gasto"] is not None]
    bien = [d["gasto"] for d in dias if d["sueno_ok"] is True and d["gasto"] is not None]
    if len(mal) < MIN_GRUPO or len(bien) < MIN_GRUPO:
        return None
    m_mal, m_bien = statistics.median(mal), statistics.median(bien)
    if m_bien > 0 and (m_mal - m_bien) / m_bien >= DELTA_GASTO:
        return (f"Las noches que duermes mal, al otro día gastas más: mediana {finanzas.clp(m_mal)} "
                f"vs {finanzas.clp(m_bien)} cuando duermes bien (sobre {len(mal)} y {len(bien)} días).")
    return None


ANALIZADORES = [
    ("sueño↔ánimo", _analizar_sueno_animo),
    ("sueño↔gasto", _analizar_sueno_gasto),
]


async def correr() -> dict:
    """Lee Diario + gasto por día, corre los cruces validados y crea inferencias (idempotente).
    Degrada elegante: si una fuente falla, no rompe. Devuelve {creadas, dias}."""
    try:
        diario = await salud.diario_reciente(60)
        gpd = await finanzas.gasto_por_dia(60)
    except Exception:
        logger.exception("correlador: no pude leer los datos")
        return {"creadas": 0, "dias": 0}

    dias = _dias_con_dato(diario, gpd)
    con_sueno = [d for d in dias if d["sueno_ok"] is not None]
    if len(con_sueno) < MIN_DIAS:  # guardia: aún no hay historial para cruzar
        logger.info("Correlador: %d/%d días con sueño — junto datos, no infiero aún.", len(con_sueno), MIN_DIAS)
        return {"creadas": 0, "dias": len(con_sueno)}

    creadas = 0
    for nombre, analizar in ANALIZADORES:
        try:
            inferencia = analizar(dias)
            if inferencia and await memory.crear_inferencia_si_nueva(inferencia, "correlador"):
                creadas += 1
                logger.info("Correlador: cruce nuevo (%s).", nombre)
        except Exception:
            logger.exception("correlador: falló el cruce %s", nombre)
    return {"creadas": creadas, "dias": len(con_sueno)}
