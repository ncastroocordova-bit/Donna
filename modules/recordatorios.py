"""Módulo Recordatorios. Tools `rec_` (Plan_Construccion_v7 Paso 1.6).

Sobre la hoja `Recordatorios` de Vida_v6. Dos tipos:
- mensual: cae un día del mes (ej. la contadora el 5, el IVA el 12).
- anual: cae una fecha fija (ej. una patente, un cumpleaños).

`rec_proximos(dias)` devuelve los que caen dentro del aviso anticipado. El campo
`Ultimo_Aviso` evita repetir el mismo aviso el mismo día.

Columnas (Guía Parte B): Recordatorio · Tipo · Dia_Fecha · Monto_Aprox · Aviso_Dias · Activo · Ultimo_Aviso.
"""
import json
import logging
from datetime import datetime, timedelta

from anthropic import AsyncAnthropic

from config import settings
from core import sheets

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

HOJA = "Recordatorios"
ACTIVO_OK = ("sí", "si", "true", "x", "1", "")  # vacío = activo por defecto


def _hoy():
    return datetime.now(settings.tz).date()


def _num(v) -> int:
    try:
        return int(float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip()))
    except (ValueError, TypeError):
        return 0


def _dias_hasta(rec: dict) -> int | None:
    """Días desde hoy hasta la próxima ocurrencia del recordatorio. None si no se puede parsear."""
    hoy = _hoy()
    tipo = str(rec.get("Tipo", "")).strip().lower()
    valor = str(rec.get("Dia_Fecha", "")).strip()
    try:
        if tipo.startswith("mens"):
            dia = int(_num(valor) or int(valor))
            # próxima ocurrencia de ese día del mes
            cand = hoy.replace(day=min(dia, 28))
            if cand < hoy:
                mes = cand.month % 12 + 1
                anio = cand.year + (1 if mes == 1 else 0)
                cand = cand.replace(year=anio, month=mes)
            return (cand - hoy).days
        if tipo.startswith("anu"):
            # acepta 'DD-MM', 'DD/MM' o 'YYYY-MM-DD'
            partes = valor.replace("/", "-").split("-")
            if len(partes) == 3:
                d = datetime.strptime(valor.replace("/", "-"), "%Y-%m-%d").date()
                d = d.replace(year=hoy.year)
            else:
                dd, mm = int(partes[0]), int(partes[1])
                d = datetime(hoy.year, mm, dd).date()
            if d < hoy:
                d = d.replace(year=hoy.year + 1)
            return (d - hoy).days
    except (ValueError, TypeError):
        return None
    return None


def _activo(rec: dict) -> bool:
    return str(rec.get("Activo", "")).strip().lower() in ACTIVO_OK


# ───────────────────────── Lectura ─────────────────────────

async def proximos(dias: int = 3) -> list[dict]:
    """Recordatorios cuya próxima ocurrencia cae dentro de `dias` (o de su Aviso_Dias)."""
    filas = await sheets.get_dicts(HOJA)
    out = []
    for r in filas:
        if not str(r.get("Recordatorio", "")).strip() or not _activo(r):
            continue
        falta = _dias_hasta(r)
        if falta is None:
            continue
        aviso = _num(r.get("Aviso_Dias")) or dias
        if falta <= aviso:
            out.append({**r, "_falta": falta})
    out.sort(key=lambda r: r["_falta"])
    return out


async def _marcar_avisado(recordatorio: str) -> None:
    try:
        await sheets.upsert_por_clave(HOJA, "Recordatorio", recordatorio, "Ultimo_Aviso", _hoy().strftime("%Y-%m-%d"))
    except Exception:
        logger.exception("No pude marcar Ultimo_Aviso de %s", recordatorio)


async def texto_proximos(dias: int = 3, marcar: bool = False) -> str:
    """Frase lista para el brief. Si marcar=True, registra Ultimo_Aviso para no repetir."""
    try:
        prox = await proximos(dias)
    except Exception:
        logger.exception("rec_proximos falló")
        return ""
    if not prox:
        return ""
    lineas = []
    for r in prox:
        falta = r["_falta"]
        cuando = "hoy" if falta == 0 else ("mañana" if falta == 1 else f"en {falta} días")
        monto = _num(r.get("Monto_Aprox"))
        cola = f" (~${monto:,.0f})" if monto else ""
        lineas.append(f"{r['Recordatorio']} {cuando}{cola}")
        if marcar:
            await _marcar_avisado(r["Recordatorio"])
    return "Recordatorios: " + "; ".join(lineas) + "."


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_proximos(inp: dict) -> str:
    dias = _num(inp.get("dias", 7)) or 7
    txt = await texto_proximos(dias)
    return txt or f"No hay recordatorios en los próximos {dias} días."


async def _t_agregar(inp: dict) -> str:
    texto = str(inp.get("texto", "")).strip()
    if not texto:
        return "¿Qué te recuerdo y cuándo?"
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=200,
            system=(
                "Extraes un recordatorio de una frase en español chileno. Devuelve SOLO JSON con: "
                "recordatorio (string corto), tipo ('mensual' si es un día del mes que se repite, "
                "'anual' si es una fecha fija), dia_fecha (el día del mes como número, o la fecha 'DD-MM'), "
                "monto_aprox (número o 0), aviso_dias (cuántos días antes avisar, default 2)."
            ),
            messages=[{"role": "user", "content": texto}],
        )
        d = json.loads(r.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        await sheets.append_row(HOJA, [
            d.get("recordatorio", texto), d.get("tipo", "mensual"), str(d.get("dia_fecha", "")),
            d.get("monto_aprox", 0), d.get("aviso_dias", 2), "Sí", "",
        ])
        return f"Anotado: te recuerdo '{d.get('recordatorio', texto)}'. Yo me encargo."
    except Exception:
        logger.exception("rec_agregar falló")
        return "No pude crear el recordatorio ahora. Reintenta en un rato."


TOOLS = [
    {
        "name": "rec_proximos",
        "description": "OBLIGATORIO cuando Nico pregunta qué recordatorios o pagos tiene cerca. Lee los reales y devuelve los que caen dentro del aviso. No inventes.",
        "input_schema": {"type": "object", "properties": {"dias": {"type": "integer", "description": "Ventana en días (default 7)"}}},
    },
    {
        "name": "rec_agregar",
        "description": "OBLIGATORIO cuando Nico pide que le recuerdes algo ('recuérdame X el 5', 'avísame del pago de Y'). Crea el recordatorio.",
        "input_schema": {
            "type": "object",
            "properties": {"texto": {"type": "string", "description": "La frase tal cual la dijo Nico"}},
            "required": ["texto"],
        },
    },
]

HANDLERS = {
    "rec_proximos": _t_proximos,
    "rec_agregar": _t_agregar,
}
