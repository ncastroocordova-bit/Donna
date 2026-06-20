"""Módulo Finanzas — el delta de v7. Tools y flujos `fin_*`. Contrato de módulo (§7).

Tres sub-flujos (Plan_Construccion_v7 Paso 1.5):

(A) Registro pasivo durante el día, en CONTEXTO AISLADO (una llamada Claude por ítem):
    `procesar_correo(raw)` y `procesar_foto(img)` extraen {fecha,tipo,categoria,comercio,
    monto,medio} con su mejor apuesta de categoría y los acumulan en el BUFFER del día
    (Supabase) con ID_Único anti-duplicado. NO escriben a Sheets todavía.

(B) Digest nocturno: `armar_digest()` devuelve la lista del día pre-categorizada marcando
    las dudosas; `confirmar_digest(correcciones)` aplica los cambios y ESCRIBE a
    Finanzas_vigente!Transacciones. La UI (panel + "Aceptar todo" / tap por línea) vive en flows.py.

(C) Faro de deuda: `estado_deuda()` lee las celdas ya calculadas de 'Tarjetas de Crédito'
    (deuda real B85, intereses muertos B86, % utilización D9/semáforo G9, total a pagar B87).
    Es el FRENO: antes de cualquier compra en cuotas, Donna muestra el costo real de la deuda.

El saldo del mes y el presupuesto se leen del 'Dashboard' (la planilla los calcula sola).
"""
import base64
import json
import logging
from datetime import datetime

from anthropic import AsyncAnthropic

from config import settings
from core import correo, memory, sheets

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

# ───────────────────────── Remitentes de gasto que Donna entiende ─────────────────────────
# Cada uno: dominios del remitente + medio de pago + pista para el extractor.
SENDERS = [
    {
        "nombre": "Banco de Chile",
        "dominios": ["bancochile.cl", "bancoedwards.cl"],
        "medio": "Banco de Chile",
        "hint": ("Banco de Chile avisa compras y cargos con tarjeta y transferencias. El asunto suele decir "
                 "'Realizaste una compra', 'Cargo en tu cuenta' o 'Comprobante de transferencia'. Saca el monto "
                 "en pesos, el comercio, la fecha y, si está, los 4 últimos dígitos de la tarjeta (a subcategoria)."),
    },
    {
        "nombre": "Mach",
        "dominios": ["somosmach.com", "mach.cl"],
        "medio": "Mach",
        "hint": ("Mach (BCI) avisa pagos y transferencias: 'Pagaste $X en COMERCIO', 'Recibiste $X de NOMBRE'. "
                 "Si el dinero ENTRA es Ingreso; si sale es Gasto."),
    },
    {
        "nombre": "Copec Pay",
        "dominios": ["copec.cl", "copecpay.cl"],
        "medio": "Copec Pay",
        "hint": ("Copec Pay confirma cargas de combustible y compras en estaciones/tienda Copec. Suele ser "
                 "categoría Transporte/Combustible. Saca monto, estación o comercio, y fecha."),
    },
    {
        "nombre": "MercadoPago",
        "dominios": ["mercadopago.com", "mercadopago.cl", "mercadolibre.com"],
        "medio": "MercadoPago",
        "hint": ("MercadoPago avisa pagos y cobros: 'Pagaste $X', 'Compraste', 'Te enviaron dinero'. Si entra "
                 "plata es Ingreso. Ignora correos de promoción/marketing (esos no son transacción: monto 0)."),
    },
]
_DOMINIOS = [d for s in SENDERS for d in s["dominios"]]


def gmail_query_gastos() -> str:
    return "from:(" + " OR ".join(_DOMINIOS) + ")"


def outlook_dominios_gastos() -> list[str]:
    return list(_DOMINIOS)


def _detectar_sender(remitente: str) -> dict | None:
    rem = (remitente or "").lower()
    for s in SENDERS:
        if any(d in rem for d in s["dominios"]):
            return s
    return None

HOJA_TX = "Transacciones"
HOJA_CAT = "Categorias"
HOJA_DASH = "Dashboard"
HOJA_TARJETAS = "Tarjetas de Crédito"

# Celdas fijas del faro (la planilla las calcula; Donna solo las lee). Guía Parte C.
CELDA_DEUDA_REAL = "B85"        # deuda tarjetas + deuda línea
CELDA_INTERESES_MUERTOS = "B86"  # interés rotativo + interés línea: plata que pagas y no baja deuda
CELDA_UTILIZACION = "D9"        # deuda total ÷ cupo total (%)
CELDA_SEMAFORO = "G9"           # 🔴/🟡/🟢
CELDA_TOTAL_PAGAR = "B87"       # cuotas + rotativo + mantención

# Celdas del Dashboard (saldo del mes corriendo).
CELDA_INGRESOS = "A6"
CELDA_GASTOS = "C6"
CELDA_BALANCE = "E6"
CELDA_LLEGO_FIN_MES = "A9"


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _num(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def _id_unico(fecha: str, monto, comercio: str) -> str:
    return f"{fecha}_{int(_num(monto))}_{(comercio or '')[:20].strip()}"


# ───────────────────────── (A) Registro pasivo → buffer (contexto aislado) ─────────────────────────

EXTRACTOR_SYSTEM = (
    "Extraes datos de boletas, transferencias y avisos de transacción chilenos (Banco de Chile, "
    "Mach, MercadoPago). Devuelve SOLO un JSON, sin texto extra, con estos campos: "
    "tipo ('Gasto' o 'Ingreso'), monto (número entero en pesos, sin separadores), "
    "categoria (tu mejor apuesta), subcategoria, comercio, medio (Banco de Chile/Mach/MP/débito/crédito/transferencia), "
    "dudosa (true si NO estás seguro de la categoría), motivo_duda (si dudosa: la pregunta corta, ej '¿Tecnología o Suscripción?'). "
    "Si no logras leer un monto, devuelve monto 0."
)


def _parse_json(texto: str) -> dict:
    t = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(t)


async def _bufferizar(datos: dict, fuente: str) -> dict | None:
    """Normaliza la extracción y la mete al buffer del día. Devuelve el dict guardado o None."""
    monto = datos.get("monto", 0)
    if _num(monto) <= 0:
        return None
    fecha = datos.get("fecha") or _hoy()
    comercio = datos.get("comercio", "")
    tx = {
        "fecha": fecha,
        "tipo": "Ingreso" if str(datos.get("tipo", "")).lower().startswith("ing") else "Gasto",
        "categoria": datos.get("categoria", "Otros"),
        "subcategoria": datos.get("subcategoria", ""),
        "comercio": comercio,
        "monto": int(_num(monto)),
        "medio": datos.get("medio", ""),
        "fuente": fuente,
        "id_unico": _id_unico(fecha, monto, comercio),
        "dudosa": bool(datos.get("dudosa", False)),
        "motivo_duda": datos.get("motivo_duda", ""),
    }
    nuevo = await memory.buffer_agregar(tx)
    return tx if nuevo else None


async def procesar_foto(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Vision AISLADA sobre una boleta → buffer del día. Degrada a None si falla."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=EXTRACTOR_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Extrae los datos de este comprobante."},
                ],
            }],
        )
        return await _bufferizar(_parse_json(r.content[0].text), "foto")
    except Exception:
        logger.exception("procesar_foto falló")
        return None


async def procesar_correo(raw: str, remitente: str = "", asunto: str = "") -> dict | None:
    """Parseo AISLADO de un correo de gasto → buffer del día. Usa la pista del remitente
    (Banco de Chile/Mach/Copec Pay/MercadoPago) para afinar la extracción."""
    sender = _detectar_sender(remitente)
    system = EXTRACTOR_SYSTEM + (f"\n\nContexto del remitente ({sender['nombre']}): {sender['hint']}" if sender else "")
    contenido = (f"Remitente: {remitente}\nAsunto: {asunto}\n\n{raw}").strip()
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": f"Extrae la transacción de este correo:\n\n{contenido}"}],
        )
        datos = _parse_json(r.content[0].text)
        if sender and not str(datos.get("medio", "")).strip():
            datos["medio"] = sender["medio"]  # el medio de pago sale del remitente
        return await _bufferizar(datos, "correo")
    except Exception:
        logger.exception("procesar_correo falló")
        return None


async def ingerir_gastos_email(max_n: int = 25) -> dict:
    """Trae los correos de gasto recientes (Gmail + Outlook), saltando los ya vistos,
    los parsea en contexto aislado y los deja en el buffer del día. Devuelve {revisados, nuevos}."""
    if not correo.disponible():
        return {"revisados": 0, "nuevos": 0}
    try:
        msgs = await correo.obtener_gastos(gmail_query_gastos(), outlook_dominios_gastos(), max_n)
    except Exception:
        logger.exception("ingerir_gastos_email: no pude leer los correos")
        return {"revisados": 0, "nuevos": 0}
    nuevos = 0
    for m in msgs:
        try:
            if await memory.correo_visto(m["proveedor"], m["id"]):
                continue
            datos = await procesar_correo(m["texto"], m.get("remitente", ""), m.get("asunto", ""))
            await memory.marcar_correo_visto(m["proveedor"], m["id"], "gasto")
            if datos:
                nuevos += 1
        except Exception:
            logger.exception("ingerir_gastos_email: falló un correo")
    if nuevos:
        logger.info("Correos de gasto ingeridos al buffer: %d nuevos de %d revisados.", nuevos, len(msgs))
    return {"revisados": len(msgs), "nuevos": nuevos}


# ───────────────────────── (B) Digest nocturno ─────────────────────────

async def armar_digest(fecha: str | None = None) -> dict:
    """Lista del día pre-categorizada. Devuelve:
    {movimientos: [{id, tipo, categoria, comercio, monto, medio, dudosa, motivo_duda}],
     total: int, n: int, n_dudosas: int}."""
    fecha = fecha or _hoy()
    try:
        pendientes = await memory.buffer_pendientes(fecha)
    except Exception:
        logger.exception("armar_digest: no pude leer el buffer")
        return {"movimientos": [], "total": 0, "n": 0, "n_dudosas": 0}
    movimientos = [{
        "id": p["id"],
        "tipo": p.get("tipo", "Gasto"),
        "categoria": p.get("categoria", "Otros"),
        "comercio": p.get("comercio", ""),
        "monto": int(_num(p.get("monto"))),
        "medio": p.get("medio", ""),
        "dudosa": bool(p.get("dudosa")),
        "motivo_duda": p.get("motivo_duda", ""),
    } for p in pendientes]
    total = sum(m["monto"] for m in movimientos if m["tipo"] == "Gasto")
    return {
        "movimientos": movimientos,
        "total": total,
        "n": len(movimientos),
        "n_dudosas": sum(1 for m in movimientos if m["dudosa"]),
    }


async def confirmar_digest(correcciones: dict | None = None) -> dict:
    """Aplica correcciones (por id de buffer: {categoria, monto, descartar}) y ESCRIBE las
    confirmadas a Finanzas_vigente!Transacciones. Devuelve {escritas, descartadas}."""
    correcciones = correcciones or {}
    fecha = _hoy()
    pendientes = await memory.buffer_pendientes(fecha)
    escritas = descartadas = 0
    for p in pendientes:
        corr = correcciones.get(p["id"], {})
        if corr.get("descartar"):
            await memory.buffer_marcar(p["id"], "descartada")
            descartadas += 1
            continue
        categoria = corr.get("categoria", p.get("categoria", "Otros"))
        monto = corr.get("monto", p.get("monto", 0))
        try:
            await sheets.append_row(HOJA_TX, [
                p.get("fecha", fecha), p.get("tipo", "Gasto"), categoria,
                p.get("subcategoria", ""), p.get("comercio", ""), int(_num(monto)),
                p.get("medio", ""), p.get("fuente", ""), p.get("id_unico", ""),
            ], sheet_id=sheets.fin_id())
            await memory.buffer_marcar(p["id"], "confirmada")
            escritas += 1
        except Exception:
            logger.exception("confirmar_digest: no pude escribir una transacción")
    return {"escritas": escritas, "descartadas": descartadas}


# ───────────────────────── (C) Faro de deuda (el freno) ─────────────────────────

async def estado_deuda() -> dict:
    """Lee las celdas ya calculadas del faro. Degrada campo a campo si una falla."""
    fin = sheets.fin_id()

    async def _leer(celda):
        try:
            return await sheets.get_celda(HOJA_TARJETAS, celda, sheet_id=fin)
        except Exception:
            logger.exception("estado_deuda: no pude leer %s", celda)
            return ""

    deuda = _num(await _leer(CELDA_DEUDA_REAL))
    intereses = _num(await _leer(CELDA_INTERESES_MUERTOS))
    util_raw = await _leer(CELDA_UTILIZACION)
    util = _num(util_raw)
    if 0 < util <= 1:  # por si viene como fracción (0.79) en vez de 79
        util *= 100
    semaforo = (await _leer(CELDA_SEMAFORO)).strip() or ("🔴" if util > 70 else "🟡" if util > 30 else "🟢")
    total_pagar = _num(await _leer(CELDA_TOTAL_PAGAR))
    return {
        "deuda_total_real": deuda,
        "intereses_muertos": intereses,
        "utilizacion": util,
        "semaforo": semaforo,
        "total_a_pagar": total_pagar,
    }


def formatear_deuda(d: dict) -> str:
    return (
        f"Deuda real ${d['deuda_total_real']:,.0f}. De este mes, ${d['intereses_muertos']:,.0f} "
        f"son solo interés — plata que pagas y no baja ni un peso de la deuda. "
        f"Utilización {d['utilizacion']:.0f}% {d['semaforo']}. Total a pagar ${d['total_a_pagar']:,.0f}."
    )


# ───────────────────────── Saldo del mes / presupuesto (lectura del Dashboard) ─────────────────────────

async def saldo_mes() -> dict:
    fin = sheets.fin_id()

    async def _leer(celda):
        try:
            return await sheets.get_celda(HOJA_DASH, celda, sheet_id=fin)
        except Exception:
            return ""

    return {
        "ingresos": _num(await _leer(CELDA_INGRESOS)),
        "gastos": _num(await _leer(CELDA_GASTOS)),
        "balance": _num(await _leer(CELDA_BALANCE)),
        "llego_fin_mes": (await _leer(CELDA_LLEGO_FIN_MES)).strip(),
    }


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_registrar_gasto(inp: dict) -> str:
    """Ad-hoc por chat: 'gasté X'. Va al BUFFER del día (no a Sheets); se confirma en el cierre."""
    monto = _num(inp.get("monto", 0))
    if monto <= 0:
        return "¿Cuánto fue? Pásame el monto y lo dejo listo para el cierre."
    tipo = "Ingreso" if str(inp.get("tipo", "")).lower().startswith("ing") else "Gasto"
    fecha = _hoy()
    comercio = inp.get("comercio", "")
    tx = {
        "fecha": fecha, "tipo": tipo, "categoria": inp.get("categoria", "Otros"),
        "comercio": comercio, "monto": int(monto), "medio": inp.get("medio", ""),
        "fuente": "manual", "id_unico": _id_unico(fecha, monto, comercio),
    }
    try:
        nuevo = await memory.buffer_agregar(tx)
        verbo = "Ingreso" if tipo == "Ingreso" else "Gasto"
        if not nuevo:
            return f"Ese {verbo.lower()} ya lo tenía anotado para hoy. No lo duplico."
        return f"{verbo} de ${monto:,.0f} anotado. Lo confirmas en el cierre de hoy junto al resto."
    except Exception:
        logger.exception("fin_registrar_gasto falló")
        return "No pude anotarlo ahora. Reintenta en un rato."


async def _t_saldo_mes(inp: dict) -> str:
    try:
        s = await saldo_mes()
        cola = s["llego_fin_mes"] or (f"te sobran ${s['balance']:,.0f}" if s["balance"] >= 0 else f"negativo por ${-s['balance']:,.0f}")
        return f"Este mes: ingresos ${s['ingresos']:,.0f}, gastos ${s['gastos']:,.0f}, balance ${s['balance']:,.0f}. {cola}"
    except Exception:
        logger.exception("fin_saldo_mes falló")
        return "No pude leer el saldo del mes ahora."


async def _t_presupuesto(inp: dict) -> str:
    try:
        filas = await sheets.get_rows(HOJA_DASH, "B13:D25", sheet_id=sheets.fin_id())
        lineas = []
        for f in filas:
            if not f or not str(f[0]).strip():
                continue
            cat = f[0]
            gastado = _num(f[1]) if len(f) > 1 else 0
            pct = f[2] if len(f) > 2 else ""
            lineas.append(f"{cat}: ${gastado:,.0f} ({pct})")
        return "Presupuesto del mes:\n" + "\n".join(lineas) if lineas else "Aún no hay gastos contra presupuesto este mes."
    except Exception:
        logger.exception("fin_presupuesto falló")
        return "No pude leer el presupuesto ahora."


async def _t_estado_deuda(inp: dict) -> str:
    try:
        return formatear_deuda(await estado_deuda())
    except Exception:
        logger.exception("fin_estado_deuda falló")
        return "No pude leer el estado de la deuda ahora."


async def _t_armar_digest(inp: dict) -> str:
    d = await armar_digest()
    if d["n"] == 0:
        return "Hoy no detecté movimientos. El digest está limpio."
    lineas = [
        f"- {m['comercio'] or m['categoria']}: ${m['monto']:,.0f} → {m['categoria']}"
        + (f"  ⚠️ {m['motivo_duda']}" if m["dudosa"] else "")
        for m in d["movimientos"]
    ]
    return f"Hoy detecté {d['n']} movimiento(s) (${d['total']:,.0f}):\n" + "\n".join(lineas)


# ───────────────────────── Señal destilada (brief) ─────────────────────────

async def senal_finanzas() -> str:
    """Conclusión corta para el brief: saldo corriendo + señal de deuda si aprieta."""
    partes = []
    try:
        s = await saldo_mes()
        if s["ingresos"] or s["gastos"]:
            partes.append(f"balance del mes ${s['balance']:,.0f}")
    except Exception:
        logger.exception("senal_finanzas: saldo falló")
    try:
        d = await estado_deuda()
        if d["intereses_muertos"] > 0:
            partes.append(f"intereses muertos ${d['intereses_muertos']:,.0f} {d['semaforo']}")
    except Exception:
        logger.exception("senal_finanzas: deuda falló")
    return "Plata: " + "; ".join(partes) + "." if partes else ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "fin_registrar_gasto",
        "description": (
            "OBLIGATORIO cuando Nico cuenta por chat que gastó o recibió plata ('gasté X', 'pagué X en Y', "
            "'me pagaron'). Lo anota en el BUFFER del día — NO se escribe a la planilla todavía: Nico lo "
            "confirma en el digest del cierre de las 22:00. Por defecto es Gasto; tipo='Ingreso' solo si la plata ENTRA."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["Gasto", "Ingreso"]},
                "monto": {"type": "number", "description": "Monto en pesos, sin separadores"},
                "categoria": {"type": "string"},
                "comercio": {"type": "string"},
                "medio": {"type": "string", "description": "Banco de Chile, Mach, MP, efectivo, débito, crédito, transferencia"},
            },
            "required": ["monto"],
        },
    },
    {
        "name": "fin_saldo_mes",
        "description": "OBLIGATORIO antes de hablar del saldo o balance del mes. Lee el Dashboard ya calculado (ingresos, gastos, balance, si llega a fin de mes). No inventes cifras.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_presupuesto",
        "description": "OBLIGATORIO cuando Nico pregunta cómo va respecto al presupuesto o si se está pasando en una categoría. Lee el bloque por categoría del Dashboard. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_estado_deuda",
        "description": (
            "OBLIGATORIO cuando Nico pregunta por su deuda/tarjetas/cupo, Y OBLIGATORIO antes de que se "
            "comprometa con cualquier compra EN CUOTAS (es el freno). Devuelve deuda real, intereses muertos "
            "del mes, % de utilización y total a pagar. No inventes montos."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_armar_digest",
        "description": "Muestra el digest del día (movimientos pendientes de confirmar) si Nico lo pide antes del cierre.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "fin_registrar_gasto": _t_registrar_gasto,
    "fin_saldo_mes": _t_saldo_mes,
    "fin_presupuesto": _t_presupuesto,
    "fin_estado_deuda": _t_estado_deuda,
    "fin_armar_digest": _t_armar_digest,
}
