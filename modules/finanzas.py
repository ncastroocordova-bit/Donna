"""Módulo Finanzas. Contrato de módulo (Plan v5 §8). Tools `fin_*`.

Rediseñado sobre la planilla real de Nico. Hojas:
- Transacciones: Fecha, Tipo (Gasto/Ingreso), Categoria, Subcategoria, Comercio, Monto, Medio, Fuente, ID_Unico
- Categorias:    Categoria, Tipo, Presupuesto (límite mensual de gasto), Notas
- Tarjetas:      Concepto, Banco_de_Chile, Mach, Total (matriz: cupo/deuda)
- Presupuesto:   Fuente, Monto, Tipo, Notas (fuentes de ingreso esperado)

El trabajo pesado (Vision sobre boleta) corre en contexto AISLADO. Degradación elegante.
"""
import base64
import json
import logging
from datetime import datetime

from anthropic import AsyncAnthropic

import sheets
from config import settings

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _num(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def _id_unico(fecha: str, monto, comercio: str) -> str:
    return f"{fecha}_{int(_num(monto))}_{(comercio or '')[:20].strip()}"


async def _escribir_transaccion(tipo, categoria, subcategoria, comercio, monto, medio, fuente) -> None:
    fecha = _hoy()
    await sheets.append_row("Transacciones", [
        fecha, tipo, categoria, subcategoria, comercio, monto, medio, fuente,
        _id_unico(fecha, monto, comercio),
    ])


# ───────────────────────── Handlers de tools ─────────────────────────

async def _registrar_transaccion(inp: dict) -> str:
    tipo = "Ingreso" if str(inp.get("tipo", "")).lower().startswith("ing") else "Gasto"
    monto = inp.get("monto", 0)
    cat = inp.get("categoria", "Otros")
    try:
        await _escribir_transaccion(
            tipo, cat, inp.get("subcategoria", ""), inp.get("comercio", ""),
            monto, inp.get("medio", ""), inp.get("fuente", "manual"),
        )
        verbo = "Ingreso" if tipo == "Ingreso" else "Gasto"
        return f"{verbo} de ${_num(monto):,.0f} registrado en {cat}."
    except Exception:
        logger.exception("fin_registrar_transaccion falló")
        return "No pude escribir la transacción en la planilla. Reintenta en un rato."


async def _gastos_por_categoria(mes: str) -> dict:
    txs = await sheets.get_dicts("Transacciones")
    out: dict[str, float] = {}
    for t in txs:
        if str(t.get("Tipo", "")).lower().startswith("gas") and str(t.get("Fecha", "")).startswith(mes):
            out[t.get("Categoria", "Otros")] = out.get(t.get("Categoria", "Otros"), 0) + _num(t.get("Monto"))
    return out


async def _get_balance(inp: dict) -> str:
    try:
        txs = await sheets.get_dicts("Transacciones")
        mes = _hoy()[:7]
        g = sum(_num(t.get("Monto")) for t in txs if str(t.get("Tipo", "")).lower().startswith("gas") and str(t.get("Fecha", "")).startswith(mes))
        i = sum(_num(t.get("Monto")) for t in txs if str(t.get("Tipo", "")).lower().startswith("ing") and str(t.get("Fecha", "")).startswith(mes))
        return f"Este mes: ingresos ${i:,.0f}, gastos ${g:,.0f}, balance ${i - g:,.0f}."
    except Exception:
        logger.exception("fin_get_balance falló")
        return "No pude calcular el balance ahora."


async def _get_presupuesto(inp: dict) -> str:
    try:
        cats = await sheets.get_dicts("Categorias")
        limites = {c.get("Categoria"): _num(c.get("Presupuesto")) for c in cats if _num(c.get("Presupuesto")) > 0}
        gastado = await _gastos_por_categoria(_hoy()[:7])
        lineas = []
        for cat, limite in limites.items():
            g = gastado.get(cat, 0)
            if g == 0:
                continue
            pct = g / limite * 100 if limite else 0
            flag = " ⚠️" if pct >= 100 else (" (ojo)" if pct >= 80 else "")
            lineas.append(f"{cat}: ${g:,.0f}/${limite:,.0f} ({pct:.0f}%){flag}")
        if not lineas:
            return "Aún no hay gastos cargados este mes contra el presupuesto."
        return "Presupuesto del mes:\n" + "\n".join(lineas)
    except Exception:
        logger.exception("fin_get_presupuesto falló")
        return "No pude leer el presupuesto ahora."


async def _get_tarjetas(inp: dict) -> str:
    try:
        filas = await sheets.get_dicts("Tarjetas")
        def buscar(sub):
            return next((f for f in filas if sub in str(f.get("Concepto", "")).lower()), None)
        deuda = buscar("deuda total")
        disp = buscar("cupo disponible")
        partes = []
        if deuda:
            partes.append(f"deuda ${_num(deuda.get('Total')):,.0f} (BdC ${_num(deuda.get('Banco_de_Chile')):,.0f} + Mach ${_num(deuda.get('Mach')):,.0f})")
        if disp:
            partes.append(f"cupo disponible ${_num(disp.get('Total')):,.0f}")
        return "Tarjetas: " + "; ".join(partes) + "." if partes else "No encontré datos de tarjetas."
    except Exception:
        logger.exception("fin_get_tarjetas falló")
        return "No pude leer las tarjetas ahora."


# ───────────────────────── Vision en contexto aislado ─────────────────────────

async def procesar_imagen(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Extrae datos de una boleta con una llamada AISLADA a Claude y registra la transacción."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=(
                "Extraes datos de boletas/transferencias chilenas. Devuelve SOLO un JSON con: "
                "monto (número, sin separadores), categoria (string), subcategoria (string), "
                "comercio (string), medio (string). Sin texto extra."
            ),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Extrae los datos de este comprobante."},
                ],
            }],
        )
        texto = r.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        datos = json.loads(texto)
        await _escribir_transaccion(
            "Gasto", datos.get("categoria", "Otros"), datos.get("subcategoria", ""),
            datos.get("comercio", ""), datos.get("monto", 0), datos.get("medio", ""), "foto",
        )
        return datos
    except Exception:
        logger.exception("procesar_imagen falló")
        return {}


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_finanzas() -> str:
    """Conclusión corta para el brief: categorías sobregiradas + deuda de tarjetas."""
    try:
        partes = []
        cats = await sheets.get_dicts("Categorias")
        limites = {c.get("Categoria"): _num(c.get("Presupuesto")) for c in cats if _num(c.get("Presupuesto")) > 0}
        gastado = await _gastos_por_categoria(_hoy()[:7])
        sobregiradas = [c for c, l in limites.items() if gastado.get(c, 0) > l]
        if sobregiradas:
            partes.append("te pasaste del presupuesto en " + ", ".join(sobregiradas))
        filas = await sheets.get_dicts("Tarjetas")
        deuda = next((f for f in filas if "deuda total" in str(f.get("Concepto", "")).lower()), None)
        if deuda and _num(deuda.get("Total")) > 0:
            partes.append(f"deuda de tarjetas ${_num(deuda.get('Total')):,.0f}")
        return "Plata: " + "; ".join(partes) + "." if partes else ""
    except Exception:
        logger.exception("senal_finanzas falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "fin_registrar_transaccion",
        "description": (
            "OBLIGATORIO cuando Nico cuenta que gastó o recibió plata. Registra una transacción "
            "(gasto o ingreso). Por defecto es gasto; tipo='Ingreso' solo si la plata ENTRA. "
            "Sin esta llamada NO queda registrada. Jamás confirmes el registro sin ejecutarla."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["Gasto", "Ingreso"], "description": "Gasto (default) o Ingreso"},
                "monto": {"type": "number", "description": "Monto en pesos, sin separadores"},
                "categoria": {"type": "string", "description": "Categoría (ej. Alimentación, Transporte, Chanchería)"},
                "subcategoria": {"type": "string"},
                "comercio": {"type": "string", "description": "Comercio o detalle"},
                "medio": {"type": "string", "description": "Banco de Chile, Mach, efectivo, débito, crédito, transferencia"},
                "fuente": {"type": "string", "description": "Para ingresos: de dónde viene"},
            },
            "required": ["monto"],
        },
    },
    {
        "name": "fin_get_balance",
        "description": "OBLIGATORIO antes de hablar de cifras del mes. Devuelve ingresos, gastos y balance reales del mes desde Transacciones. Cualquier número sin llamarla es inventado.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_get_presupuesto",
        "description": "OBLIGATORIO cuando Nico pregunta cómo va respecto al presupuesto, o si se está pasando en alguna categoría. Compara lo gastado por categoría este mes contra su límite. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_get_tarjetas",
        "description": "OBLIGATORIO cuando Nico pregunta por sus tarjetas, su deuda o su cupo disponible. Lee la matriz real de Tarjetas. No inventes montos de deuda.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "fin_registrar_transaccion": _registrar_transaccion,
    "fin_get_balance": _get_balance,
    "fin_get_presupuesto": _get_presupuesto,
    "fin_get_tarjetas": _get_tarjetas,
}
