"""Módulo Salud. Contrato de módulo. Tools `sal_` (Plan_Construccion_v7 Paso 1.4 + E8 v2).

Sobre la hoja `Diario`: una fila por día. Donna busca/crea la fila del día y setea la
columna. Salud es el eje #1 (el sueño es salud).

v2 (E8) suma ventanas de ayuno+sueño (Primera_Comida + Hora_Despertar; Última_Comida
y Hora_Dormi ya existían), peso (se pregunta cada cierre), un score % de hábitos y
eventos contextuales — sin inflar el cierre (toques + conversación, un panel). El
score/ventanas/peso de la semana se escriben en `Semanal` (lectura; el domingo, vía
`generar_resumen_semanal`, disparado por `core/scheduler.py`).

Columnas (Donna_Canonico.xlsx, Diario fila 2): Fecha · Ejercicio · Meditación ·
Última comida · Sueño 7h+ · Ánimo (1-4) · Hora dormí · MITs de mañana · Brief ✓ ·
Cierre ✓ · Excepción · Notas · Primera comida · Hora desperté · Agua · Proteína · Peso (kg) ·
MITs cumplidos. Agua/Proteína quedan como columnas legado (ya no se preguntan en el cierre).
Las columnas `MITs de mañana`/`MITs cumplidos` quedan como legado sin uso: el
backlog de MITs ahora vive en `Tareas` (Tipo=MIT), no en el texto libre de Diario — ver la
sección "MITs" más abajo.

MITs: un MIT no resuelto NO desaparece — queda pendiente en `Tareas` hasta que lo marcas hecho,
sin importar cuántos días pasen (a propósito, sin tope). El cierre los muestra TODOS (de hoy +
acumulados) para marcarlos uno a uno; el brief de las 8:00 los separa en "de hoy" vs "acumulados"
(solo informa, no pide nada).
"""
import logging
import re
import statistics
from datetime import datetime, timedelta

from config import settings
from core import memory, sheets

logger = logging.getLogger(__name__)

HOJA = "Diario"
HOJA_SEMANAL = "Semanal"

# campo conversacional → columna real en la hoja (nombres EXACTOS del canon Donna_Canonico.xlsx).
COLS = {
    "ejercicio": "Ejercicio",
    "meditacion": "Meditación",
    "ultima_comida": "Última comida",
    "sueno_7h": "Sueño 7h+",
    "animo": "Ánimo (1-4)",
    "hora_dormi": "Hora dormí",
    "brief": "Brief ✓",
    "cierre": "Cierre ✓",
    "excepcion": "Excepción",
    "notas": "Notas",
    # --- v2 (E8) ---
    "primera_comida": "Primera comida",
    "hora_despertar": "Hora desperté",
    "agua": "Agua",
    "proteina": "Proteína",
    "peso": "Peso (kg)",
}
COLS_SEMANAL = {
    "score_habitos": "Score hábitos",
    "ventana_comida": "Ventana comida",
    "ventana_sueno": "Ventana sueño",
    "peso": "Peso",
}
# Hábitos binarios (presencia = cumplido) → admiten racha y default "Sí".
BINARIOS = ("ejercicio", "meditacion")
# Hábitos que el cierre pregunta por toque (ejercicio/meditación/última comida = panel único,
# ver core/flows.py teclado_cierre). Agua/proteína se sacaron del cierre (ya no se preguntan).
HABITOS_TOQUE = ("ejercicio", "meditacion", "ultima_comida")
# Composición del score semanal de hábitos (default del canon, E8).
HABITOS_SCORE = ("ejercicio", "meditacion", "sueno_7h")
# Campos de hora libres (conversacionales, sal_set_hora) — Hora_Dormi tiene su propio tool
# (sal_registrar_sueno) porque va junto con el sueno_7h.
CAMPOS_HORA = ("primera_comida", "ultima_comida", "hora_despertar")


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _lunes_de_semana(fecha=None) -> str:
    """Fecha (YYYY-MM-DD) del lunes de la semana de `fecha` (hoy si no se pasa)."""
    d = fecha or datetime.now(settings.tz).date()
    lunes = d - timedelta(days=d.weekday())
    return lunes.strftime("%Y-%m-%d")


_AFIRMATIVO = {"sí", "si", "✓", "x", "true", "1", "hecho", "hice"}


def _afirmativo(v) -> bool:
    """¿La celda marca el hábito como HECHO? 'No' (o vacío) cuenta como no hecho — así el
    'Hoy no' explícito queda registrado pero no rompe ni alimenta la racha. Admite también
    hábitos anotados como CANTIDAD: cualquier número > 0 cuenta como cumplido ese día."""
    s = str(v).strip().lower()
    if s in _AFIRMATIVO:
        return True
    try:
        return float(s) > 0
    except ValueError:
        return False


async def _set(campo: str, valor, fecha: str | None = None) -> str:
    fecha = fecha or _hoy()
    return await sheets.upsert_por_clave(HOJA, "Fecha", fecha, COLS[campo], valor)


# ───────────────────────── Funciones directas (botones del panel) ─────────────────────────

async def marcar_habito(campo: str, valor=None, fecha: str | None = None) -> str:
    campo = campo.lower()
    if campo not in COLS:
        return f"No conozco el hábito '{campo}'."
    if valor in (None, ""):
        valor = "Sí" if campo in BINARIOS else valor
    estado = await _set(campo, valor, fecha)
    if estado not in ("actualizado", "creado"):
        return f"No pude anotar {campo}: {estado}."
    extra = f" Racha: {await calcular_racha(campo)} día(s)." if campo in BINARIOS else ""
    return f"Anotado: {campo.replace('_', ' ')} ({valor}).{extra}"


async def registrar_animo(valor, fecha: str | None = None) -> str:
    await _set("animo", valor, fecha)
    return f"Ánimo {valor}/4 anotado."


async def registrar_sueno(horas_7plus, hora_dormi: str = "") -> str:
    await _set("sueno_7h", horas_7plus)
    if hora_dormi:
        await _set("hora_dormi", hora_dormi)
    return "Sueño anotado."


async def registrar_mits(texto: str) -> str:
    """Anoche dictaste tus MITs de mañana → se crean como filas en `Tareas` (Tipo=MIT,
    Fecha objetivo=mañana). No se arrastran por texto en Diario: viven en Tareas hasta que
    los marques hechos, sin importar cuántos días pase."""
    items = _parsear_mits(texto)
    if not items:
        return "No te pillé ningún MIT ahí. Dímelos de nuevo, uno por uno."
    manana = _manana()
    for item in items:
        await sheets.append_row(HOJA_TAREAS, [_hoy(), item, "—", TIPO_MIT, manana, "Pendiente", "", ""])
    return f"{len(items)} MIT(s) para mañana anotados."


# ───────────────────────── MITs: backlog real en Tareas, sin arrastre invisible ─────────────
# Un MIT no resuelto NO desaparece solo — queda pendiente en Tareas (Tipo=MIT) hasta que lo
# marques hecho, sin importar cuántos días pasen (sin límite, a propósito). El cierre los
# muestra TODOS (de hoy + acumulados) para marcarlos uno a uno; el brief de las 8:00 los separa
# en "de hoy" (Fecha objetivo = hoy) vs "acumulados" (de antes), solo para informar.

HOJA_TAREAS = "Tareas"
TIPO_MIT = "MIT"
COLS_TAREAS = {
    "creada": "Creada", "descripcion": "Descripción", "proyecto": "Proyecto", "tipo": "Tipo",
    "fecha_objetivo": "Fecha objetivo", "estado": "Estado", "completada": "Completada", "notas": "Notas",
}


def _manana() -> str:
    return (datetime.now(settings.tz).date() + timedelta(days=1)).strftime("%Y-%m-%d")


def _parsear_mits(texto: str) -> list[str]:
    """Hasta 3 MITs desde el texto libre dictado. Separa por coma/punto y coma/salto de línea
    y limpia un 'y' colgante al final de un ítem (ej. '..., y comprar pan' -> 'comprar pan').
    No inventa: si no logra separar nada, devuelve [] (no un ítem vacío)."""
    if not texto or not str(texto).strip():
        return []
    partes = re.split(r"[;\n,]", str(texto).strip())
    limpio = []
    for p in partes:
        p = p.strip(" .")
        p = re.sub(r"^y\s+", "", p, flags=re.I)
        if p:
            limpio.append(p)
    return limpio[:3]


async def _mits_pendientes_raw() -> list[dict]:
    """Filas de Tareas Tipo=MIT sin completar, con su fecha objetivo. Ordenadas de más vieja
    a más nueva (lo más atrasado aparece primero)."""
    filas = await sheets.get_dicts(HOJA_TAREAS)
    pend = [
        f for f in filas
        if str(f.get(COLS_TAREAS["tipo"], "")).strip() == TIPO_MIT
        and not str(f.get(COLS_TAREAS["completada"], "")).strip()
        and str(f.get(COLS_TAREAS["descripcion"], "")).strip()
    ]
    pend.sort(key=lambda f: str(f.get(COLS_TAREAS["creada"], "")))
    return [
        {"descripcion": str(f.get(COLS_TAREAS["descripcion"], "")).strip(),
         "fecha_objetivo": str(f.get(COLS_TAREAS["fecha_objetivo"], "")).strip()}
        for f in pend
    ]


async def mits_pendientes() -> list[str]:
    """Todos los MITs sin resolver (de hoy + acumulados), para el panel del cierre — cada uno
    se marca por separado; si no lo marcas, sigue apareciendo mañana."""
    return [m["descripcion"] for m in await _mits_pendientes_raw()]


async def _fila_mit(texto: str, buscar_completada: bool):
    """Ubica la fila de Tareas para ese MIT exacto (Tipo=MIT, completada/no según se pida).
    Devuelve (nº de fila 1-based, índices de columna) o None."""
    filas = await sheets.get_rows(HOJA_TAREAS)
    h_idx, headers = sheets._fila_headers(filas)
    if h_idx < 0:
        return None
    idx = {c: headers.index(v) for c, v in COLS_TAREAS.items() if v in headers}
    if not all(k in idx for k in ("descripcion", "tipo", "completada")):
        return None

    def _get(fila, col):
        i = idx[col]
        return str(fila[i]).strip() if len(fila) > i else ""

    for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
        if _get(fila, "descripcion") == texto.strip() and _get(fila, "tipo") == TIPO_MIT:
            if bool(_get(fila, "completada")) == buscar_completada:
                return n, idx
    return None


async def marcar_mit(texto: str, hecho: bool) -> bool:
    """Marca (o desmarca) un MIT como hecho en Tareas. Devuelve si encontró la fila."""
    encontrada = await _fila_mit(texto, buscar_completada=not hecho)
    if not encontrada:
        return False
    n, idx = encontrada
    await sheets.set_cell(HOJA_TAREAS, n, idx["completada"], "Sí" if hecho else "")
    return True


async def senal_mits_brief() -> str:
    """Para el brief de las 8:00 (solo lectura): separa los MITs de HOY (Fecha objetivo = hoy)
    de los acumulados de antes. Silencio si no hay ninguno pendiente."""
    try:
        hoy = _hoy()
        todos = await _mits_pendientes_raw()
        if not todos:
            return ""
        de_hoy = [m["descripcion"] for m in todos if m["fecha_objetivo"] == hoy]
        acumulados = [m["descripcion"] for m in todos if m["fecha_objetivo"] != hoy]
        partes = []
        if de_hoy:
            partes.append(f"MITs de hoy: {', '.join(de_hoy)}")
        if acumulados:
            partes.append(f"MITs acumulados sin resolver ({len(acumulados)}): {', '.join(acumulados)}")
        return ". ".join(partes) + "." if partes else ""
    except Exception:
        logger.exception("senal_mits_brief falló")
        return ""


# ───────────────────────── v2 (E8): horas, peso, eventos ─────────────────────────

async def registrar_hora(campo: str, hora: str, fecha: str | None = None) -> str:
    """Primera_Comida / Ultima_Comida / Hora_Despertar por chat o voz (HH:MM)."""
    campo = campo.lower()
    if campo not in CAMPOS_HORA:
        return f"No anoto horas para '{campo}'."
    if not str(hora).strip():
        return "¿A qué hora? Dime la hora y la dejo anotada."
    await _set(campo, hora, fecha)
    return f"{campo.replace('_', ' ').capitalize()} a las {hora}, anotado."


async def registrar_hora_dormi(hora: str, fecha: str | None = None) -> str:
    """Hora en que Nico se durmió. Va con el sueño (por eso no pasa por CAMPOS_HORA, que es
    para las horas conversacionales sueltas). Se escribe en la fila del día."""
    if _parse_hora(str(hora)) is None:
        return "¿A qué hora te dormiste? Dame la hora en HH:MM."
    await _set("hora_dormi", hora, fecha)
    return f"Anotado: te dormiste {hora}."


async def derivar_sueno_de_ventana(fecha: str | None = None) -> str | None:
    """Calcula la ventana de sueño (dormí→desperté) de la fila del día y setea 'Sueño 7h+'
    (Sí/No) SOLO — reemplaza la pregunta binaria inútil por el dato real. Devuelve 'Sí'/'No',
    o None si falta alguna de las dos horas. Degrada elegante si no puede leer el Diario."""
    fecha = fecha or _hoy()
    try:
        filas = await sheets.get_dicts(HOJA)
    except Exception:
        logger.exception("derivar_sueno_de_ventana: no pude leer Diario")
        return None
    fila = next((f for f in filas if str(f.get("Fecha", "")).strip() == fecha), None)
    if not fila:
        return None
    mins = _ventana_minutos(str(fila.get(COLS["hora_dormi"], "")).strip(),
                            str(fila.get(COLS["hora_despertar"], "")).strip())
    if mins is None:
        return None
    val = "Sí" if mins >= 7 * 60 else "No"
    await _set("sueno_7h", val, fecha)
    return val


_EVENTO_NULO = {"no", "nada", "no pasó nada", "no paso nada", "ninguna", "ninguno", "todo normal", "nada raro"}


async def registrar_peso(kg) -> str:
    """Se pregunta en cada cierre (22:00) — igual acepta el registro cualquier día que Nico lo diga."""
    try:
        valor = float(str(kg).replace(",", "."))
    except (TypeError, ValueError):
        return "¿Cuántos kilos? Pásame el número y lo anoto."
    if valor <= 0:
        return "Ese peso no me cuadra. Dime el número de nuevo."
    await _set("peso", valor)
    return f"Peso anotado: {valor} kg."


async def evento_contextual(texto: str) -> str:
    """Lo que Nico no controló hoy → memoria episódica, tag `evento_externo`. El correlador
    trata ese día como CONTEXTO, no como patrón (guardia anti-patrón-falso). Si dice que no
    pasó nada, no guarda nada — no hay evento que registrar."""
    limpio = str(texto or "").strip().lower().rstrip(".")
    if not limpio or limpio in _EVENTO_NULO:
        return ""
    await memory.guardar_memoria(texto.strip(), dominio="evento_externo", forzar=True)
    return "Anotado como algo fuera de tu control hoy — no lo cuento como patrón, es contexto."


async def marcar_excepcion() -> str:
    await _set("excepcion", "Sí")
    return "Día de excepción marcado. La racha no se rompe."


async def marcar_brief() -> None:
    await _set("brief", "✓")


async def marcar_cierre() -> None:
    await _set("cierre", "✓")


# ───────────────────────── Cálculos ─────────────────────────

async def calcular_racha(campo: str) -> int:
    """Días consecutivos hasta hoy con la columna del hábito no vacía."""
    filas = await sheets.get_dicts(HOJA)
    col = COLS[campo]
    hechos = {str(f.get("Fecha", "")) for f in filas if _afirmativo(f.get(col, ""))}
    racha = 0
    d = datetime.now(settings.tz).date()
    while d.strftime("%Y-%m-%d") in hechos:
        racha += 1
        d -= timedelta(days=1)
    return racha


async def _ultimos(dias: int) -> list[dict]:
    filas = await sheets.get_dicts(HOJA)
    desde = (datetime.now(settings.tz).date() - timedelta(days=dias)).strftime("%Y-%m-%d")
    return [f for f in filas if str(f.get("Fecha", "")) >= desde]


async def diario_reciente(dias: int = 60) -> list[dict]:
    """Filas del Diario de los últimos `dias` (interfaz pública para el correlador de la espina)."""
    return await _ultimos(dias)


# ───────────────────────── v2 (E8): ventanas de ayuno + sueño ─────────────────────────

def _parse_hora(hhmm: str) -> int | None:
    """'HH:MM' → minutos desde medianoche, o None si no se puede leer (no inventa)."""
    s = str(hhmm or "").strip()
    if not s or ":" not in s:
        return None
    try:
        h, m = s.split(":")[:2]
        h, m = int(h), int(m)
        if not (0 <= h < 24 and 0 <= m < 60):
            return None
        return h * 60 + m
    except ValueError:
        return None


def _ventana_minutos(inicio: str, fin: str) -> int | None:
    """Minutos entre `inicio` y `fin` (HH:MM). Cruza medianoche si `fin` <= `inicio`
    (ej. dormí 23:30 → desperté 07:00 = 7h30, no un número negativo)."""
    i, f = _parse_hora(inicio), _parse_hora(fin)
    if i is None or f is None:
        return None
    if f <= i:
        f += 24 * 60
    return f - i


def _fmt_minutos(m: float | None) -> str:
    if m is None:
        return "—"
    m = round(m)
    return f"{m // 60}h{m % 60:02d}" if m % 60 else f"{m // 60}h"


def _calcular_ventanas(filas: list[dict]) -> dict:
    """Mediana de ventana de comida (primera→última) y de sueño (dormir→despertar),
    semana vs fin de semana. Un día sin ambas horas de un par no entra a esa mediana
    (no inventa). Devuelve minutos crudos (para escribir/comparar) + texto formateado."""
    comida = {"semana": [], "finde": []}
    sueno = {"semana": [], "finde": []}
    for f in filas:
        try:
            d = datetime.strptime(str(f.get("Fecha", "")).strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        grupo = "finde" if d.weekday() >= 5 else "semana"
        vc = _ventana_minutos(f.get(COLS["primera_comida"], ""), f.get(COLS["ultima_comida"], ""))
        if vc is not None:
            comida[grupo].append(vc)
        vs = _ventana_minutos(f.get(COLS["hora_dormi"], ""), f.get(COLS["hora_despertar"], ""))
        if vs is not None:
            sueno[grupo].append(vs)
    out = {}
    for nombre, datos in (("comida", comida), ("sueno", sueno)):
        for grupo, valores in datos.items():
            mediana = statistics.median(valores) if valores else None
            out[f"{nombre}_{grupo}"] = mediana
            out[f"{nombre}_{grupo}_n"] = len(valores)
            out[f"{nombre}_{grupo}_txt"] = _fmt_minutos(mediana)
    return out


async def resumen_ventanas(dias: int = 7) -> dict:
    """Interfaz pública: mediana de ventanas sobre los últimos `dias` días. Solo mide y
    muestra — sin meta ni empuje (canon: calla hasta tener baseline)."""
    return _calcular_ventanas(await _ultimos(dias))


# ───────────────────────── v2 (E8): score semanal de hábitos ─────────────────────────

def _calcular_score(filas: list[dict]) -> dict:
    """% de hábitos cumplidos sobre los días con fila (sueño 7h, ejercicio, meditación).
    Cuadra 1:1 con los toques: cada 'Sí' de cada hábito, cada día, suma."""
    total = len(filas) * len(HABITOS_SCORE)
    if total == 0:
        return {"score": None, "cumplidos": 0, "total": 0}
    cumplidos = sum(
        1 for f in filas for campo in HABITOS_SCORE if _afirmativo(f.get(COLS[campo], ""))
    )
    return {"score": round(100 * cumplidos / total), "cumplidos": cumplidos, "total": total}


async def score_semana(dias: int = 7) -> dict:
    return _calcular_score(await _ultimos(dias))


# ───────────────────────── v2 (E8): resumen semanal → Semanal (domingo) ─────────────────────────

def _lecturas_peso(filas: list[dict]) -> list[tuple[str, float]]:
    """(fecha, kg) de las filas con peso legible, ordenadas por fecha ascendente. Ignora las
    celdas que no son un número (no inventa)."""
    out = []
    for f in filas:
        v = str(f.get(COLS["peso"], "")).strip()
        if not v:
            continue
        try:
            out.append((str(f.get("Fecha", "")).strip(), float(v.replace(",", "."))))
        except ValueError:
            continue
    out.sort(key=lambda t: t[0])
    return out


async def _ultimo_peso(filas: list[dict]) -> str:
    """Última lectura de peso disponible (no falla si esta semana no hubo registro)."""
    lecturas = _lecturas_peso(filas)
    return _fmt_peso(lecturas[-1][1]) if lecturas else ""


def _fmt_peso(kg: float) -> str:
    """Sin decimal de más: 78 en vez de 78.0, pero 77.5 se mantiene."""
    return str(int(kg)) if float(kg).is_integer() else str(round(kg, 1))


def _peso_actual_y_delta(filas: list[dict]) -> tuple[float | None, float | None]:
    """Último peso registrado y su cambio vs la lectura anterior separada ≥5 días (para que el
    delta sea semana-a-semana y no dos pesajes del mismo día). delta=None si no hay con qué
    comparar. No inventa: si solo hay una lectura, delta queda en None."""
    lecturas = _lecturas_peso(filas)
    if not lecturas:
        return None, None
    fecha_act, peso_act = lecturas[-1]
    try:
        d_act = datetime.strptime(fecha_act, "%Y-%m-%d").date()
    except ValueError:
        return peso_act, None
    for fecha, kg in reversed(lecturas[:-1]):
        try:
            d_ref = datetime.strptime(fecha, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (d_act - d_ref).days >= 5:
            return peso_act, round(peso_act - kg, 1)
    return peso_act, None


async def generar_resumen_semanal() -> dict:
    """Domingo: calcula score + ventanas + último peso (con su tendencia) y los escribe en
    `Semanal` (lectura; el modelo no vive en el Sheet). Disparado por core/scheduler.py.
    Idempotente (upsert). Devuelve las piezas para armar el mensaje dominical a Nico."""
    semana_clave = _lunes_de_semana()
    filas = await _ultimos(7)
    score = _calcular_score(filas)
    ventanas = _calcular_ventanas(filas)
    filas90 = await _ultimos(90)  # se pregunta cada cierre; mira más atrás para tendencia
    peso = await _ultimo_peso(filas90)
    peso_actual, peso_delta = _peso_actual_y_delta(filas90)

    async def _w(campo: str, valor) -> None:
        await sheets.upsert_por_clave(HOJA_SEMANAL, "Semana (lunes)", semana_clave, COLS_SEMANAL[campo], valor)

    if score["score"] is not None:
        await _w("score_habitos", f"{score['score']}%")
    ventana_comida = f"L-V {ventanas['comida_semana_txt']} · S-D {ventanas['comida_finde_txt']}"
    ventana_sueno = f"L-V {ventanas['sueno_semana_txt']} · S-D {ventanas['sueno_finde_txt']}"
    await _w("ventana_comida", ventana_comida)
    await _w("ventana_sueno", ventana_sueno)
    if peso:
        await _w("peso", peso)
    return {"semana": semana_clave, "score": score, "ventanas": ventanas,
            "peso": peso, "peso_actual": peso_actual, "peso_delta": peso_delta}


def texto_revision_semanal(r: dict) -> str:
    """Bloque de datos EXACTOS de la semana (para el mensaje dominical). Sin LLM: los números
    son los que son; la voz la pone quien lo envuelva (scheduler → brain). '' si no hay nada
    que mostrar todavía (semana sin datos)."""
    lineas = []
    s = r.get("score", {})
    if s.get("score") is not None:
        lineas.append(f"Score de hábitos: {s['score']}% ({s['cumplidos']}/{s['total']}).")
    v = r.get("ventanas", {})
    if v.get("comida_semana_n") or v.get("comida_finde_n"):
        lineas.append(f"Ventana de comida: L-V {v['comida_semana_txt']} · S-D {v['comida_finde_txt']}.")
    if v.get("sueno_semana_n") or v.get("sueno_finde_n"):
        lineas.append(f"Ventana de sueño: L-V {v['sueno_semana_txt']} · S-D {v['sueno_finde_txt']}.")
    pa, pd = r.get("peso_actual"), r.get("peso_delta")
    if pa is not None:
        if pd is None:
            lineas.append(f"Peso: {_fmt_peso(pa)} kg.")
        elif pd == 0:
            lineas.append(f"Peso: {_fmt_peso(pa)} kg (igual que la lectura anterior).")
        else:
            signo = "+" if pd > 0 else ""
            lineas.append(f"Peso: {_fmt_peso(pa)} kg ({signo}{pd} vs la anterior).")
    return "\n".join(f"• {l}" for l in lineas)


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_marcar_habito(inp: dict) -> str:
    try:
        return await marcar_habito(str(inp.get("habito", "")), inp.get("valor"))
    except Exception:
        logger.exception("sal_marcar_habito falló")
        return "No pude escribir el hábito ahora."


async def _t_registrar_animo(inp: dict) -> str:
    try:
        return await registrar_animo(inp.get("valor"))
    except Exception:
        logger.exception("sal_registrar_animo falló")
        return "No pude anotar el ánimo ahora."


async def _t_registrar_sueno(inp: dict) -> str:
    try:
        return await registrar_sueno(inp.get("horas_7plus", inp.get("valor", "")), inp.get("hora_dormi", ""))
    except Exception:
        logger.exception("sal_registrar_sueno falló")
        return "No pude anotar el sueño ahora."


async def _t_racha(inp: dict) -> str:
    campo = str(inp.get("habito", "")).lower()
    if campo not in COLS:
        return f"No conozco el hábito '{campo}'."
    try:
        return f"Racha de {campo.replace('_', ' ')}: {await calcular_racha(campo)} día(s) seguidos."
    except Exception:
        logger.exception("sal_racha falló")
        return "No pude calcular la racha."


async def _t_resumen_semana(inp: dict) -> str:
    try:
        recientes = await _ultimos(7)
        partes = []
        for c in ("ejercicio", "meditacion"):
            n = sum(1 for f in recientes if _afirmativo(f.get(COLS[c], "")))
            partes.append(f"{c}: {n}/7")
        n_sueno = sum(1 for f in recientes if str(f.get(COLS["sueno_7h"], "")).strip().lower() in ("sí", "si", "true", "x"))
        partes.append(f"sueño 7h+: {n_sueno}/7")
        animos = [float(f.get(COLS["animo"], 0) or 0) for f in recientes if str(f.get(COLS["animo"], "")).strip()]
        if animos:
            partes.append(f"ánimo prom {sum(animos) / len(animos):.1f}/4")
        return "Últimos 7 días — " + ", ".join(partes) + "." if partes else "Sin registros esta semana."
    except Exception:
        logger.exception("sal_resumen_semana falló")
        return "No pude armar el resumen."


async def _t_set_hora(inp: dict) -> str:
    try:
        return await registrar_hora(str(inp.get("campo", "")), str(inp.get("hora", "")))
    except Exception:
        logger.exception("sal_set_hora falló")
        return "No pude anotar la hora ahora."


async def _t_peso(inp: dict) -> str:
    try:
        return await registrar_peso(inp.get("kg", inp.get("valor", "")))
    except Exception:
        logger.exception("sal_peso falló")
        return "No pude anotar el peso ahora."


async def _t_resumen_ventanas(inp: dict) -> str:
    try:
        v = await resumen_ventanas(7)
        if not (v["comida_semana_n"] or v["comida_finde_n"] or v["sueno_semana_n"] or v["sueno_finde_n"]):
            return "Todavía no tengo suficientes horas de comida/despertar registradas para medir ventanas."
        return (
            f"Ventana de comida — semana: {v['comida_semana_txt']} ({v['comida_semana_n']} día(s)), "
            f"finde: {v['comida_finde_txt']} ({v['comida_finde_n']} día(s)). "
            f"Ventana de sueño — semana: {v['sueno_semana_txt']} ({v['sueno_semana_n']} día(s)), "
            f"finde: {v['sueno_finde_txt']} ({v['sueno_finde_n']} día(s)). Solo mido, sin meta todavía."
        )
    except Exception:
        logger.exception("sal_resumen_ventanas falló")
        return "No pude calcular las ventanas ahora."


async def _t_score_semana(inp: dict) -> str:
    try:
        s = await score_semana(7)
        if s["score"] is None:
            return "Sin datos esta semana para el score."
        return f"Score de hábitos de la semana: {s['score']}% ({s['cumplidos']}/{s['total']} toques)."
    except Exception:
        logger.exception("sal_score_semana falló")
        return "No pude calcular el score ahora."


async def _t_evento_contextual(inp: dict) -> str:
    try:
        r = await evento_contextual(str(inp.get("texto", "")))
        return r or "Ok."
    except Exception:
        logger.exception("sal_evento_contextual falló")
        return "No pude anotarlo ahora."


# ───────────────────────── Señal destilada (el eje #1) ─────────────────────────

async def senal_salud() -> str:
    """Cruza sueño × ánimo y devuelve una frase corta. Esta es la señal madre de Donna."""
    try:
        recientes = await _ultimos(5)
        recientes.sort(key=lambda f: str(f.get("Fecha", "")))
        noches_tarde = 0
        for f in reversed(recientes):  # racha de noches recientes con poco sueño
            val = str(f.get(COLS["sueno_7h"], "")).strip().lower()
            if val and val not in ("sí", "si", "true", "x", "1"):
                noches_tarde += 1
            elif val:
                break
        if noches_tarde >= 3:
            return f"{noches_tarde}ª noche seguida con poco sueño; el patrón sueño→ánimo se está activando."
        for h in BINARIOS:
            r = await calcular_racha(h)
            if r >= 3:
                return f"{h.replace('_', ' ')} en racha de {r} días."
        return ""
    except Exception:
        logger.exception("senal_salud falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "sal_marcar_habito",
        "description": (
            "OBLIGATORIO cuando Nico dice que cumplió un hábito del día: ejercicio, meditación, o a qué hora "
            "comió por última vez (ayuno). Anota en la fila del día. Sin esta llamada NO queda registrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "habito": {"type": "string", "enum": list(HABITOS_TOQUE)},
                "valor": {"type": "string", "description": "Para ultima_comida: la hora (ej '21:30'). El resto: 'Sí'/'No', o se omite (default Sí)."},
            },
            "required": ["habito"],
        },
    },
    {
        "name": "sal_registrar_animo",
        "description": "OBLIGATORIO cuando Nico reporta su ánimo. Anota el ánimo del día (1 a 4).",
        "input_schema": {
            "type": "object",
            "properties": {"valor": {"type": "integer", "minimum": 1, "maximum": 4}},
            "required": ["valor"],
        },
    },
    {
        "name": "sal_registrar_sueno",
        "description": "OBLIGATORIO cuando Nico cuenta cuánto durmió o a qué hora se acostó. Anota si durmió 7h+ y la hora en que se durmió.",
        "input_schema": {
            "type": "object",
            "properties": {
                "horas_7plus": {"type": "string", "description": "'Sí' si durmió 7h o más, 'No' si menos"},
                "hora_dormi": {"type": "string", "description": "Hora a la que se durmió (ej '01:15')"},
            },
            "required": ["horas_7plus"],
        },
    },
    {
        "name": "sal_racha",
        "description": "OBLIGATORIO antes de decir cuántos días seguidos lleva con un hábito (ejercicio, meditación). Lo computa real. No inventes el número.",
        "input_schema": {
            "type": "object",
            "properties": {"habito": {"type": "string", "enum": list(BINARIOS)}},
            "required": ["habito"],
        },
    },
    {
        "name": "sal_resumen_semana",
        "description": "Resume cuántos días de los últimos 7 cumplió cada hábito + ánimo promedio. Para una mirada general.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "sal_set_hora",
        "description": (
            "OBLIGATORIO cuando Nico dice a qué hora comió por primera vez, comió por última vez, o a qué "
            "hora despertó (sin mezclar con la hora en que se durmió — esa es sal_registrar_sueno)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campo": {"type": "string", "enum": list(CAMPOS_HORA)},
                "hora": {"type": "string", "description": "Hora HH:MM, ej '08:15'"},
            },
            "required": ["campo", "hora"],
        },
    },
    {
        "name": "sal_peso",
        "description": (
            "OBLIGATORIO cuando Nico dice cuánto pesa o pesó ('peso 78 kilos', 'esta semana 77.5'). "
            "Se pregunta cada cierre, pero anótalo cualquier día que lo diga."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"kg": {"type": "number", "description": "Peso en kilos"}},
            "required": ["kg"],
        },
    },
    {
        "name": "sal_resumen_ventanas",
        "description": "OBLIGATORIO cuando Nico pregunta por su ventana de comida (ayuno) o de sueño, o cómo le está yendo con eso. Da la mediana real semana vs fin de semana. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "sal_score_semana",
        "description": "OBLIGATORIO cuando Nico pregunta por su score o % de hábitos de la semana. Lo computa real. No inventes el número.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "sal_evento_contextual",
        "description": (
            "OBLIGATORIO cuando Nico cuenta que algo FUERA DE SU CONTROL afectó su día (le cambiaron una "
            "reunión, se enfermó alguien, un imprevisto le arruinó el plan). NO la llames si dice que no "
            "pasó nada o que fue un día normal — en ese caso no hay evento que registrar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"texto": {"type": "string", "description": "Lo que pasó, tal cual lo contó Nico"}},
            "required": ["texto"],
        },
    },
]

HANDLERS = {
    "sal_marcar_habito": _t_marcar_habito,
    "sal_registrar_animo": _t_registrar_animo,
    "sal_registrar_sueno": _t_registrar_sueno,
    "sal_racha": _t_racha,
    "sal_resumen_semana": _t_resumen_semana,
    "sal_set_hora": _t_set_hora,
    "sal_peso": _t_peso,
    "sal_resumen_ventanas": _t_resumen_ventanas,
    "sal_score_semana": _t_score_semana,
    "sal_evento_contextual": _t_evento_contextual,
}
