"""Módulo Salud. Contrato de módulo. Tools `salud_`.

Rediseñado sobre la matriz diaria real de Nico (hoja Habitos): una fila por día,
columnas por hábito. Donna busca/crea la fila del día y setea la columna.
"""
import logging
from datetime import datetime, timedelta

import sheets
from config import settings

logger = logging.getLogger(__name__)

HOJA = "Habitos"

# campo conversacional → columna real en la hoja.
CAMPOS = {
    "ejercicio": "Ejercicio",
    "meditacion": "Meditacion",
    "luz_solar": "Luz_Solar",
    "estudio": "Estudio",
    "sueno": "Horas_Sueno",
    "ayuno": "H_Ayuno",
    "agua": "Litros_Agua",
    "energia": "Energia",
    "estres": "Estres",
    "dormir": "Dormir",
    "despertar": "Despertar",
    "tipo_ejercicio": "Tipo_Ejercicio",
    "mit1": "MIT1", "mit2": "MIT2", "mit3": "MIT3",
    "notas": "Notas",
}
# Hábitos binarios (presencia = cumplido) → admiten racha y default "Sí".
BINARIOS = ("ejercicio", "meditacion", "luz_solar", "estudio")


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


# ───────────────────────── Handlers de tools ─────────────────────────

async def _marcar(inp: dict) -> str:
    campo = str(inp.get("campo", "")).lower()
    if campo not in CAMPOS:
        return f"No conozco el hábito '{campo}'. Son: {', '.join(CAMPOS)}."
    valor = inp.get("valor")
    if valor in (None, ""):
        valor = "Sí" if campo in BINARIOS else ""
    fecha = inp.get("fecha") or _hoy()
    try:
        estado = await sheets.upsert_por_clave(HOJA, "Fecha", fecha, CAMPOS[campo], valor)
        if estado in ("actualizado", "creado"):
            extra = ""
            if campo in BINARIOS:
                extra = f" Racha: {await _calcular_racha(campo)} día(s)."
            return f"Listo, {campo} anotado para {fecha} ({valor}).{extra}"
        return f"No pude anotar {campo}: {estado}."
    except Exception:
        logger.exception("salud_marcar falló")
        return "No pude escribir el hábito ahora."


async def _get_racha(inp: dict) -> str:
    campo = str(inp.get("habito", "")).lower()
    if campo not in CAMPOS:
        return f"No conozco el hábito '{campo}'."
    try:
        return f"Racha de {campo}: {await _calcular_racha(campo)} día(s) seguidos."
    except Exception:
        logger.exception("salud_get_racha falló")
        return "No pude calcular la racha."


async def _resumen_semana(inp: dict) -> str:
    try:
        filas = await sheets.get_dicts(HOJA)
        desde = (datetime.now(settings.tz).date() - timedelta(days=7)).strftime("%Y-%m-%d")
        recientes = [f for f in filas if str(f.get("Fecha", "")) >= desde]
        conteo = {c: sum(1 for f in recientes if str(f.get(CAMPOS[c], "")).strip()) for c in BINARIOS}
        texto = ", ".join(f"{c}: {n}/7" for c, n in conteo.items())
        return f"Últimos 7 días — {texto}." if texto else "Sin registros esta semana."
    except Exception:
        logger.exception("salud_resumen_semana falló")
        return "No pude armar el resumen."


# ───────────────────────── Cálculos ─────────────────────────

async def _calcular_racha(campo: str) -> int:
    """Días consecutivos hasta hoy con la columna del hábito no vacía."""
    filas = await sheets.get_dicts(HOJA)
    col = CAMPOS[campo]
    hechos = {str(f.get("Fecha", "")) for f in filas if str(f.get(col, "")).strip()}
    racha = 0
    d = datetime.now(settings.tz).date()
    while d.strftime("%Y-%m-%d") in hechos:
        racha += 1
        d -= timedelta(days=1)
    return racha


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_salud() -> str:
    """Rachas y caídas para el brief/cierre."""
    try:
        alertas = []
        for h in BINARIOS:
            r = await _calcular_racha(h)
            if r >= 3:
                alertas.append(f"{h} en racha de {r}")
        return "Salud: " + "; ".join(alertas) + "." if alertas else ""
    except Exception:
        logger.exception("senal_salud falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "salud_marcar",
        "description": (
            "OBLIGATORIO cuando Nico dice que cumplió un hábito o reporta un dato del día: ejercicio, "
            "meditación, luz solar, estudio, horas de sueño, horas de ayuno, litros de agua, energía/estrés (1-5), "
            "MITs del día, notas. Anota en la fila del día. Sin esta llamada NO queda registrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campo": {"type": "string", "enum": list(CAMPOS), "description": "Qué hábito/dato"},
                "valor": {"type": "string", "description": "El valor (número para sueño/ayuno/agua/energía/estrés; texto si aplica). Para hábitos binarios puede omitirse."},
                "fecha": {"type": "string", "description": "YYYY-MM-DD (default hoy)"},
            },
            "required": ["campo"],
        },
    },
    {
        "name": "salud_get_racha",
        "description": "OBLIGATORIO antes de decir cuántos días seguidos lleva con un hábito (ejercicio, meditación, luz solar, estudio). Lo computa real. No inventes el número.",
        "input_schema": {
            "type": "object",
            "properties": {"habito": {"type": "string", "enum": list(BINARIOS)}},
            "required": ["habito"],
        },
    },
    {
        "name": "salud_resumen_semana",
        "description": "Resume cuántos días de los últimos 7 cumplió cada hábito binario. Para una mirada general.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "salud_marcar": _marcar,
    "salud_get_racha": _get_racha,
    "salud_resumen_semana": _resumen_semana,
}
