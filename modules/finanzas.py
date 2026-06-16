"""Módulo Finanzas. Contrato de módulo (Plan v5 §8):
- No toca el núcleo. Se comunica por la interfaz (tools + señal destilada).
- Tools con prefijo `fin_`, descripciones sin solapamiento.
- El trabajo pesado (Vision sobre una boleta) corre en contexto AISLADO.
- Degradación elegante: si algo falla, devuelve un mensaje y Donna sigue.

Datos en Google Sheets. Hojas: GASTOS, INGRESOS, PAGOS.
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


# ───────────────────────── Handlers de tools ─────────────────────────

async def _registrar_gasto(inp: dict) -> str:
    try:
        await sheets.append_row("GASTOS", [
            _hoy(),
            inp["monto"],
            inp.get("categoria", "otros"),
            inp.get("descripcion", ""),
            inp.get("medio", ""),
        ])
        return f"Gasto de ${inp['monto']} registrado en {inp.get('categoria', 'otros')}."
    except Exception:
        logger.exception("fin_registrar_gasto falló")
        return "No pude escribir el gasto en la planilla. Reintenta en un rato."


async def _registrar_ingreso(inp: dict) -> str:
    try:
        await sheets.append_row("INGRESOS", [_hoy(), inp["monto"], inp.get("fuente", ""), inp.get("descripcion", "")])
        return f"Ingreso de ${inp['monto']} registrado."
    except Exception:
        logger.exception("fin_registrar_ingreso falló")
        return "No pude registrar el ingreso ahora."


async def _get_balance(inp: dict) -> str:
    try:
        gastos = await sheets.get_dicts("GASTOS")
        ingresos = await sheets.get_dicts("INGRESOS")
        mes = _hoy()[:7]
        tot_g = sum(_num(g.get("monto")) for g in gastos if str(g.get("fecha", "")).startswith(mes))
        tot_i = sum(_num(i.get("monto")) for i in ingresos if str(i.get("fecha", "")).startswith(mes))
        return f"Este mes: ingresos ${tot_i:,.0f}, gastos ${tot_g:,.0f}, balance ${tot_i - tot_g:,.0f}."
    except Exception:
        logger.exception("fin_get_balance falló")
        return "No pude calcular el balance ahora."


async def _get_pagos_proximos(inp: dict) -> str:
    try:
        pagos = await sheets.get_dicts("PAGOS")
        pendientes = [p for p in pagos if str(p.get("estado", "")).lower() != "pagado"]
        if not pendientes:
            return "No hay pagos pendientes registrados."
        total = sum(_num(p.get("monto")) for p in pendientes)
        detalle = ", ".join(f"{p.get('concepto', '?')} (${_num(p.get('monto')):,.0f})" for p in pendientes[:5])
        return f"Pagos próximos: {detalle}. Total ${total:,.0f}."
    except Exception:
        logger.exception("fin_get_pagos_proximos falló")
        return "No pude leer los pagos próximos."


# ───────────────────────── Vision en contexto aislado ─────────────────────────

async def procesar_imagen(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Extrae datos de una boleta/transferencia con una llamada AISLADA a Claude
    (sin la constitución ni el contexto del núcleo: solo extracción). Devuelve
    solo la conclusión destilada — el detalle nunca le tapa la ventana a Donna."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=(
                "Extraes datos de boletas/transferencias chilenas. Devuelve SOLO un JSON con: "
                "monto (número, sin separadores), categoria (string), descripcion (string), "
                "medio (string). Sin texto extra."
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
        await sheets.append_row("GASTOS", [
            _hoy(), datos.get("monto", 0), datos.get("categoria", "otros"),
            datos.get("descripcion", ""), datos.get("medio", "foto"),
        ])
        return datos
    except Exception:
        logger.exception("procesar_imagen falló")
        return {}


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_finanzas() -> str:
    """Conclusión corta para el brief. No datos crudos."""
    try:
        pagos = await sheets.get_dicts("PAGOS")
        pendientes = [p for p in pagos if str(p.get("estado", "")).lower() != "pagado"]
        por_pagar = sum(_num(p.get("monto")) for p in pendientes)
        partes = []
        if por_pagar:
            partes.append(f"hay ${por_pagar:,.0f} por pagar")

        gastos = await sheets.get_dicts("GASTOS")
        mes_actual = _hoy()[:7]
        g_mes = sum(_num(g.get("monto")) for g in gastos if str(g.get("fecha", "")).startswith(mes_actual))
        if g_mes:
            partes.append(f"llevas ${g_mes:,.0f} gastados este mes")
        return "Plata: " + "; ".join(partes) + "." if partes else ""
    except Exception:
        logger.exception("senal_finanzas falló")
        return ""


def _num(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "fin_registrar_gasto",
        "description": "Registra un gasto que Nico menciona en texto (monto, categoría, descripción, medio de pago). Úsala cuando cuenta que gastó algo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monto": {"type": "number", "description": "Monto en pesos"},
                "categoria": {"type": "string"},
                "descripcion": {"type": "string"},
                "medio": {"type": "string", "description": "efectivo, débito, crédito, transferencia"},
            },
            "required": ["monto"],
        },
    },
    {
        "name": "fin_registrar_ingreso",
        "description": "Registra un ingreso de dinero (monto, fuente). Úsala solo para plata que ENTRA, no para gastos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monto": {"type": "number"},
                "fuente": {"type": "string"},
                "descripcion": {"type": "string"},
            },
            "required": ["monto"],
        },
    },
    {
        "name": "fin_get_balance",
        "description": "OBLIGATORIO: llama esta herramienta antes de hablar de cifras mensuales. Cualquier número que cites sin llamarla es inventado. Jamás respondas sobre el balance sin obtener el dato real aquí primero.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_get_pagos_proximos",
        "description": "OBLIGATORIO: llama esta herramienta antes de responder sobre pagos pendientes. 'No hay nada por pagar' sin haberla llamado es una mentira. Jamás respondas sobre cuentas sin obtener la lista real aquí.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "fin_registrar_gasto": _registrar_gasto,
    "fin_registrar_ingreso": _registrar_ingreso,
    "fin_get_balance": _get_balance,
    "fin_get_pagos_proximos": _get_pagos_proximos,
}
