"""Evals no-destructivos del Módulo 1 (Finanzas). Puros: sin red real, sin Supabase, sin
Sheets — corren en milisegundos y no tocan datos de producción. Donde el flujo real llama
a Claude Vision o a Supabase (p.ej. `procesar_foto`), se monkeypatchea esa llamada con una
respuesta fija: se prueba la lógica determinista de Donna, no el modelo de Anthropic.

Cubren los criterios del roadmap (ficha Finanzas):
  · faro da $2.028.091 y $48.236  → formato chileno + lectura del faro.
  · "aceptar todo" escribe sin duplicar → planificador anti-duplicado del digest.
  · foto→categoría correcta → procesar_foto con Vision mockeada.

El freno-antes-de-cuota vive en los evals conversacionales (tests/casos.yaml, caso
tool_freno_cuotas) y en la semana de prueba real.
"""
import asyncio
import time
from pathlib import Path

import pytest

from modules import finanzas


# ───────────────────────── Formato de pesos chilenos ─────────────────────────

def test_clp_formato_chileno():
    assert finanzas.clp(2028091) == "$2.028.091"
    assert finanzas.clp(48236) == "$48.236"
    assert finanzas.clp(0) == "$0"
    assert finanzas.clp("15000") == "$15.000"      # acepta string
    assert finanzas.clp(999) == "$999"             # sin separador bajo mil


# ───────────────────────── Faro de deuda (las cifras del canon) ─────────────────────────

def test_faro_muestra_las_cifras_del_canon():
    d = {
        "deuda_total_real": 2028091,
        "intereses_muertos": 48236,
        "utilizacion": 79,
        "semaforo": "🔴",
        "total_a_pagar": 350000,
    }
    texto = finanzas.formatear_deuda(d)
    assert "$2.028.091" in texto       # deuda real (incluye la línea)
    assert "$48.236" in texto          # intereses muertos del mes
    assert "79%" in texto


def test_constantes_del_faro_apuntan_al_canon():
    """Ancla las celdas que lee el código al layout real de Donna_Canonico.xlsx, y verifica
    que los insumos dan las cifras del canon — la deuda real INCLUYE la línea de crédito.
    Este es el eval del roadmap: 'faro da $2.028.091 y $48.236'."""
    openpyxl = pytest.importorskip("openpyxl")
    ruta = Path(__file__).resolve().parent.parent / "docs" / "Donna_Canonico.xlsx"
    if not ruta.exists():
        pytest.skip("falta docs/Donna_Canonico.xlsx")
    wb = openpyxl.load_workbook(ruta, data_only=False)
    assert finanzas.HOJA_TARJETAS in wb.sheetnames           # 'Tarjetas y Deuda'
    ws = wb[finanzas.HOJA_TARJETAS]
    fila_deuda = finanzas.CELDA_DEUDA_REAL[1:]               # 'B4' -> '4'
    fila_int = finanzas.CELDA_INTERESES_MUERTOS[1:]
    assert "DEUDA TOTAL REAL" in str(ws[f"A{fila_deuda}"].value).upper()
    assert "INTERESES MUERTOS" in str(ws[f"A{fila_int}"].value).upper()
    # Insumos → cifras del canon (B4 = BCh + Mach + línea; B5 = interés rotativo + línea).
    deuda = ws["B29"].value + ws["B40"].value + ws["B44"].value
    intereses = round(ws["B20"].value * ws["B21"].value) + 0 + ws["B45"].value
    assert round(deuda) == 2028091
    assert round(intereses) == 48236


# ───────────────────────── Anti-duplicado del digest ("aceptar todo" sin duplicar) ─────────────────────────

def _pend(buffer_id, id_unico, **extra):
    base = {"id": buffer_id, "id_unico": id_unico, "categoria": "Otros", "monto": 1000}
    base.update(extra)
    return base


def test_aceptar_todo_escribe_los_nuevos():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_500_Uber")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert len(plan["a_escribir"]) == 2
    assert plan["duplicadas"] == []
    assert plan["a_descartar"] == []


def test_no_duplica_lo_que_ya_esta_en_la_planilla():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_500_Uber")]
    ya = {"2026-06-20_1000_Jumbo"}                  # Jumbo ya escrito antes
    plan = finanzas._planificar_digest(pendientes, {}, ya)
    escritos = [i["p"]["id"] for i in plan["a_escribir"]]
    duplicados = [p["id"] for p in plan["duplicadas"]]
    assert escritos == ["b2"]
    assert duplicados == ["b1"]


def test_no_duplica_dos_lineas_iguales_en_el_mismo_digest():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_1000_Jumbo")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert len(plan["a_escribir"]) == 1            # se escribe una sola vez
    assert len(plan["duplicadas"]) == 1


def test_descartar_no_escribe():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"descartar": True}}, set())
    assert plan["a_escribir"] == []
    assert [p["id"] for p in plan["a_descartar"]] == ["b1"]


def test_correccion_de_categoria_se_respeta():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo", categoria="Otros")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"categoria": "Supermercado"}}, set())
    assert plan["a_escribir"][0]["categoria"] == "Supermercado"


# ───────────────────────── Intención del gasto (v2) ─────────────────────────

def test_intencion_por_categoria():
    assert finanzas._intencion_de("Alimentación") == "Necesario"
    assert finanzas._intencion_de("Transporte") == "Necesario"
    assert finanzas._intencion_de("Chanchería") == "Deseo"        # comida rápida/delivery
    assert finanzas._intencion_de("Suscripciones") == "Deseo"
    assert finanzas._intencion_de("Cursos") == "Inversion"
    assert finanzas._intencion_de("") == "Necesario"              # default conservador


def test_digest_deriva_la_intencion_de_la_categoria():
    pendientes = [_pend("b1", "2026-06-20_1000_x", categoria="Alimentación")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert plan["a_escribir"][0]["intencion"] == "Necesario"


def test_corregir_categoria_recalcula_la_intencion():
    # Venía como Alimentación (Necesario); Nico la corrige a Cursos → la intención sigue.
    pendientes = [_pend("b1", "2026-06-20_1000_x", categoria="Alimentación", intencion="Necesario")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"categoria": "Cursos"}}, set())
    assert plan["a_escribir"][0]["categoria"] == "Cursos"
    assert plan["a_escribir"][0]["intencion"] == "Inversion"


def test_intencion_explicita_gana():
    pendientes = [_pend("b1", "2026-06-20_1000_x", categoria="Alimentación")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"intencion": "Deseo"}}, set())
    assert plan["a_escribir"][0]["intencion"] == "Deseo"


# ───────────────────────── Metas financieras (v2) ─────────────────────────

def test_progreso_meta():
    assert finanzas._progreso(40, 100) == 40
    assert finanzas._progreso(0, 100) == 0
    assert finanzas._progreso(150, 100) == 100        # tope en 100
    assert finanzas._progreso("$1.500", "3.000") == 50  # formato chileno
    assert finanzas._progreso(50, 0) is None           # objetivo no positivo → sin progreso


# ───────────────────────── Detalle de compra (v3): predecible / desglose / correlación ─────────────────────────

def test_predecible_despensa_si_perecible_no():
    assert finanzas._predecible("arroz") is True
    assert finanzas._predecible("atún en lata") is True
    assert finanzas._predecible("cloro gel") is True
    assert finanzas._predecible("papel higiénico") is True
    assert finanzas._predecible("pan") is False           # cotidiano/perecible
    assert finanzas._predecible("chanchería") is False
    assert finanzas._predecible("") is False              # default conservador


def test_intencion_resumen():
    assert finanzas._intencion_resumen([]) == ""
    assert finanzas._intencion_resumen([{"intencion": "Necesario"}, {"intencion": "Necesario"}]) == "Necesario"
    assert finanzas._intencion_resumen([{"intencion": "Necesario"}, {"intencion": "Deseo"}]) == "Mixto"


def test_desglose_nombre_monto():
    lineas = finanzas._desglose_determinista("arroz 1290, leche 990, chocolate 2000")
    assert [l["item"] for l in lineas] == ["arroz", "leche", "chocolate"]
    assert [l["precio"] for l in lineas] == [1290, 990, 2000]
    assert next(l for l in lineas if l["item"] == "arroz")["predecible"] is True


def test_desglose_con_resto_cuadra_al_total():
    lineas = finanzas._desglose_determinista("2000 en chanchería, el resto pan", total=5000)
    assert len(lineas) == 2
    chan = next(l for l in lineas if "chan" in l["item"].lower())
    pan = next(l for l in lineas if l["item"] == "pan")
    assert chan["precio"] == 2000 and chan["intencion"] == "Deseo" and chan["predecible"] is False
    assert pan["precio"] == 3000                          # el "resto" cuadra al total
    assert sum(l["precio"] for l in lineas) == 5000


def test_correlacion_foto_y_correo_un_solo_gasto():
    pend = [
        {"id": "foto1", "fuente": "foto", "monto": 42000, "fecha": "2026-06-20",
         "items": [{"item": "arroz", "precio": 42000, "intencion": "Necesario"}]},
        {"id": "mail1", "fuente": "correo", "monto": 42000, "fecha": "2026-06-20"},
    ]
    merges = finanzas.fin_correlacionar(pend)
    assert len(merges) == 1
    assert merges[0]["keep"] == "mail1" and merges[0]["drop"] == "foto1"   # el correo es el canónico


def test_correlacion_no_aparea_montos_distintos():
    pend = [
        {"id": "foto1", "fuente": "dictado", "monto": 42000, "fecha": "2026-06-20",
         "items": [{"item": "x", "precio": 42000}]},
        {"id": "mail1", "fuente": "correo", "monto": 9990, "fecha": "2026-06-20"},
    ]
    assert finanzas.fin_correlacionar(pend) == []


def test_digest_intencion_mixta_con_detalle():
    items = [{"intencion": "Necesario"}, {"intencion": "Deseo"}]
    pendientes = [_pend("b1", "2026-06-20_42000_super", items=items, categoria="Alimentación")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert plan["a_escribir"][0]["intencion"] == "Mixto"   # ≥2 intenciones → Mixto
    assert plan["a_escribir"][0]["items"] == items


@pytest.fixture
def _cat_real(monkeypatch):
    """Catálogo de `Categorias` como el real, para que `_validar_categoria` valide de verdad."""
    async def fake():
        return {finanzas._norm(c): c for c in
                ["Alimentación", "Chanchería", "Transporte", "Hogar", "Ropa", "Otro Gasto"]}
    monkeypatch.setattr(finanzas, "_categorias_reales", fake)


# ── Predecible (2026-07-24): el clasificador de reposición y su lookup aprendido ──

@pytest.fixture(autouse=True)
def _sin_aprendidos(monkeypatch):
    """Aísla la heurística de predecibles en TODO el archivo: cache vacía y marcada como ya
    cargada, así ningún test sale a Supabase por el lookup (los que ejercen el lookup se
    sobreescriben `_items_aprendidos` ellos mismos)."""
    monkeypatch.setattr(finanzas, "_items_aprendidos", {})
    monkeypatch.setattr(finanzas, "_predecibles_cargados", True)


def test_predecible_conoce_la_vida_de_nico(_sin_aprendidos):
    """La lista estaba afinada para una despensa genérica y no sabía que Nico tiene un hijo.
    'pañales emilio' × $29.340 salía `no` — el ítem de reposición por excelencia."""
    assert finanzas._predecible("pañales emilio") is True
    assert finanzas._predecible("toallitas humedas") is True
    assert finanzas._predecible("fórmula") is True
    # Y lo perecible/cotidiano sigue fuera del predictor por canon
    assert finanzas._predecible("pan") is False
    assert finanzas._predecible("chanchería") is False


def test_predecible_gana_la_coincidencia_mas_especifica(_sin_aprendidos):
    """Antes el NO ganaba siempre por orden de revisión, y eso rompía los compuestos: 'salsa de
    tomate' es despensa pero calzaba con 'tomate' (perecible). Ahora gana la keyword más larga."""
    assert finanzas._predecible("salsa de tomate") is True
    assert finanzas._predecible("leche en polvo") is True
    assert finanzas._predecible("tomate") is False       # el simple sigue siendo perecible
    assert finanzas._predecible("leche") is False        # la líquida es ambigua: fuera


def test_predecible_no_confunde_por_prefijo(_sin_aprendidos):
    """Las keywords con espacio final ('sal ', 'te ') existen justo para esto. El normalizador
    de ítems no puede hacer `.strip()` o vuelven los falsos positivos."""
    assert finanzas._predecible("salame") is False
    assert finanzas._predecible("tetera") is False


def test_predecible_lo_aprendido_manda_sobre_las_keywords(monkeypatch):
    """El canon de la espina: una corrección de Nico no se vuelve a inferir desde cero. El chip
    📦/🥖 existía desde v3 pero moría en ese digest — marcaba 'pañales' cada semana y Donna lo
    olvidaba. El lookup se consulta ANTES que la heurística."""
    monkeypatch.setattr(finanzas, "_items_aprendidos", {"panales": False, "cerveza": True})
    assert finanzas._predecible("pañales emilio") is False   # la keyword decía True
    assert finanzas._predecible("cervezas") is True          # la keyword decía False


def test_norm_item_no_toca_los_espacios():
    """`_norm` hace .strip() y por eso no sirve acá: convertiría 'sal ' en 'sal'."""
    assert finanzas._norm_item("Pañales ") == "panales "
    assert finanzas._norm_item("ATÚN") == "atun"


# ── Auditoría de columnas 2026-07-24: el vocabulario canónico de `Medio` ──
# La hoja tenía OCHO valores mezclando banco, producto y operación ('Banco de Chile' x18 sin
# decir débito o crédito, 'Tarjeta crédito' x11 sin decir de qué banco, 'Mach' x8 que en realidad
# eran transferencias). Ahora un solo eje: de qué cuenta salió la plata.

def test_normalizar_medio_desambigua_con_el_detalle():
    """El caso que motivó todo: 'Mach' a secas era débito O transferencia según el detalle —
    el dato que lo resolvía vivía en `Detalle_Medio`, la columna que nadie leía."""
    assert finanzas.normalizar_medio("Mach", "Transferencia a terceros") == "Transferencia"
    assert finanzas.normalizar_medio("Mach", "****1969") == "Mach débito"
    assert finanzas.normalizar_medio("Banco de Chile", "****5502") == "BCh débito"
    assert finanzas.normalizar_medio("Banco de Chile crédito (USD)", "****9371") == "BCh crédito"


def test_normalizar_medio_la_operacion_gana_al_banco():
    """'Banco de Chile transferencia' calza con banco Y con transferencia: manda la operación."""
    assert finanzas.normalizar_medio("Banco de Chile transferencia", "Rut 19986903-5") == "Transferencia"
    assert finanzas.normalizar_medio("Transferencia", "Pago de Tarjeta de Crédito") == "Transferencia"
    assert finanzas.normalizar_medio("Transferencia recibida (Itaú)") == "Transferencia"


def test_normalizar_medio_no_adivina_el_producto():
    """La regresión de las 11 filas de junio: eran BCh y Mach mezcladas, crédito las dos, y el
    código las mandaba a débito por default. Saber el banco NO es saber el producto — si falta,
    'Otro' (una pregunta visible) le gana a un 'BCh débito' inventado (una respuesta falsa)."""
    assert finanzas.normalizar_medio("Banco de Chile") == "Otro"
    assert finanzas.normalizar_medio("Mach") == "Otro"
    assert finanzas.normalizar_medio("Tarjeta crédito") == "Otro"      # crédito, pero ¿de qué banco?
    # Con el producto explícito, sí resuelve:
    assert finanzas.normalizar_medio("Banco de Chile crédito") == "BCh crédito"
    assert finanzas.normalizar_medio("Banco de Chile débito") == "BCh débito"


def test_normalizar_medio_el_numero_de_tarjeta_manda():
    """El nº de tarjeta es la señal más confiable: no depende de que el parser de turno se
    acordara de anotar el producto. Gana sobre el texto del medio."""
    assert finanzas.normalizar_medio("Banco de Chile", "****9371") == "BCh crédito"
    assert finanzas.normalizar_medio("", "****5502") == "BCh débito"
    assert finanzas.normalizar_medio("Mach", "****7160") == "Mach crédito"
    # Una tarjeta que no está en el mapa no se inventa
    assert finanzas.normalizar_medio("Banco de Chile", "****0000") == "Otro"


def test_normalizar_medio_nunca_devuelve_algo_fuera_del_catalogo():
    """La garantía dura: pase lo que pase, a la planilla llega uno de los seis. Un parser nuevo
    no puede reintroducir una etiqueta suelta."""
    for entrada in ("Mach débito", "Copec Pay", "MercadoPago", "", "cualquier cosa rara", None):
        assert finanzas.normalizar_medio(entrada or "") in finanzas.MEDIOS_CANON


# Layout de Compras_Detalle desde 2026-07-24 (7 columnas, antes 10):
#   [0] Fecha · [1] Comercio · [2] Item · [3] Precio · [4] Categoría · [5] Predecible · [6] ID_Tx
# Se fueron Cantidad (nunca se llenó), Intención y Fuente (copias del padre por ID_Tx).

def test_filas_detalle_shape(_cat_real):
    p = {"fecha": "2026-06-20", "comercio": "Súper", "id_unico": "ID1", "fuente": "foto",
         "monto": 1290}
    items = [{"item": "arroz", "cantidad": 1, "precio": 1290, "categoria": "Alimentación",
              "intencion": "Necesario", "predecible": True}]
    assert asyncio.run(finanzas._filas_detalle(p, items))[0] == [
        "2026-06-20", "Súper", "arroz", 1290, "Alimentación", "sí", "ID1"]


# ── Ola 2 · F2.1/F2.2: Compras_Detalle nunca guarda una categoría fuera del catálogo ──
# Regresión de la auditoría 2026-07-23: `_categoria_item` capitalizaba el nombre del ítem como
# categoría y metió 'Compota', 'Pan', 'Pago movida', 'Calzado', 'Bebidas' — ninguna existe en
# `Categorias`, así que sumaban $0 en toda métrica por categoría.

def test_categoria_item_no_inventa_categorias():
    assert finanzas._categoria_item("compota") == "Otro Gasto"          # antes: "Compota"
    assert finanzas._categoria_item("zapatos emi") == "Otro Gasto"      # antes: "Zapatos emi"
    assert finanzas._categoria_item("compota", "Alimentación") == "Alimentación"  # hereda del padre
    assert finanzas._categoria_item("chanchería") == "Chanchería"       # lo que sí mapea, mapea


def test_filas_detalle_valida_contra_el_catalogo(_cat_real):
    p = {"fecha": "2026-07-06", "comercio": "SUPER GANGA", "id_unico": "ID9", "fuente": "correo",
         "monto": 3109}
    items = [{"item": "compota", "precio": 1000, "categoria": "Compota"},      # inventada
             {"item": "chancheria", "precio": 2109, "categoria": "Chanchería"}]
    filas = asyncio.run(finanzas._filas_detalle(p, items, "Alimentación", "Necesario"))
    assert [f[4] for f in filas] == ["Otro Gasto", "Chanchería"]   # la fantasma cae al cajón


# ── Ola 2 · F2.5/D10: TODA transacción deja al menos una línea de detalle ──

def test_sin_items_igual_escribe_una_linea(_cat_real):
    """Un cargo suelto (bencina) también debe aparecer en Compras_Detalle: las métricas de gasto
    salen de esa hoja, así que lo que no esté ahí es invisible."""
    p = {"fecha": "2026-07-08", "comercio": "SHELL", "id_unico": "ID2", "fuente": "correo",
         "monto": 15000}
    filas = asyncio.run(finanzas._filas_detalle(p, [], "Transporte", "Necesario"))
    assert len(filas) == 1
    assert filas[0][3] == 15000 and filas[0][4] == "Transporte" and filas[0][6] == "ID2"


def test_detalle_incompleto_se_cuadra_con_linea_sin_detallar(_cat_real):
    """Si Nico detalla parte y no dice 'el resto', la diferencia NO puede quedar fuera: si no,
    SUM(detalle) != Monto y el Dashboard pierde plata en silencio al cambiar de fuente (F3.5)."""
    p = {"fecha": "2026-07-15", "comercio": "San Vale", "id_unico": "ID3", "fuente": "dictado",
         "monto": 4340}
    filas = asyncio.run(finanzas._filas_detalle(p, [{"item": "chanchería", "precio": 1840,
                                                     "categoria": "Chanchería"}], "Alimentación"))
    assert sum(f[3] for f in filas) == 4340
    assert filas[-1][2] == "(sin detallar)" and filas[-1][3] == 2500


# ── Ola 2 · F2.3: el doble conteo contra lo YA escrito en la planilla ──
# El caso real: correo el 15/07 por $4.340 (ya en la planilla) + dictado el 16/07 por lo mismo.
# `fin_correlacionar` solo mira el buffer, que se vacía en el digest de cada noche.

def _reg(idu, fecha, monto, detalle=False):
    return {"id": idu, "fecha": fecha, "monto": monto, "tiene_detalle": detalle}


def test_correlaciona_dictado_contra_transaccion_ya_escrita():
    pend = [_pend("b1", "2026-07-16_4340_SanVale", monto=4340, fecha="2026-07-16",
                  items=[{"item": "pan", "precio": 2340}], fuente="dictado")]
    regs = [_reg("2026-07-15_4340_MERCADOPAGO*SANVA", "2026-07-15", 4340)]
    out = finanzas.fin_correlacionar_registradas(pend, regs)
    assert len(out) == 1
    assert out[0]["drop"] == "b1"
    assert out[0]["adjuntar_a"] == "2026-07-15_4340_MERCADOPAGO*SANVA"


def test_no_correlaciona_si_la_transaccion_ya_tiene_detalle():
    """Si ya está itemizada, un dictado del mismo monto es otra compra, no la misma."""
    pend = [_pend("b1", "x", monto=4340, fecha="2026-07-16", items=[{"item": "pan", "precio": 4340}])]
    regs = [_reg("ID-viejo", "2026-07-15", 4340, detalle=True)]
    assert finanzas.fin_correlacionar_registradas(pend, regs) == []


def test_no_correlaciona_fuera_de_ventana_ni_por_monto_distinto():
    pend = [_pend("b1", "x", monto=4340, fecha="2026-07-25", items=[{"item": "pan", "precio": 4340}])]
    assert finanzas.fin_correlacionar_registradas(pend, [_reg("A", "2026-07-15", 4340)]) == []
    pend2 = [_pend("b2", "y", monto=9999, fecha="2026-07-16", items=[{"item": "pan", "precio": 9999}])]
    assert finanzas.fin_correlacionar_registradas(pend2, [_reg("A", "2026-07-15", 4340)]) == []


# ── Ola 5 · regresión: Fecha llega como serial de Sheets, no como texto ──
# Bug real encontrado el 2026-07-23 al validar la Ola 5 contra datos reales: Transacciones se lee
# con UNFORMATTED_VALUE, así que "Fecha" es un número de serie (46163), no "2026-05-21". Esta
# función construye el `fecha` que alimenta `_fecha_cerca()` en la 2ª pasada — sin `fecha_iso()`,
# NUNCA matcheaba en producción (el ValueError de strptime se atrapaba como "no hay match").

def test_transacciones_registradas_convierte_fecha_serial(monkeypatch):
    async def _fake_tx(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [{"ID_Único": "2026-05-21_5500_OpenAI", "Fecha": 46163, "Monto": 5500}]
    async def _fake_det(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return []
    monkeypatch.setattr(finanzas.sheets, "get_dicts",
                        lambda hoja, **kw: _fake_tx(hoja, **kw) if hoja == finanzas.HOJA_TX else _fake_det(hoja, **kw))
    out = asyncio.run(finanzas._transacciones_registradas())
    assert out[0]["fecha"] == "2026-05-21"   # no "46163"


def test_gasto_por_dia_convierte_fecha_serial(monkeypatch):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [{"Tipo": "Gasto", "Fecha": 46178, "Monto": 3109}]   # 46178 = 2026-06-05
    monkeypatch.setattr(finanzas.sheets, "get_dicts", _fake)
    out = asyncio.run(finanzas.gasto_por_dia(dias=3650))
    assert out.get("2026-06-05") == 3109
    assert "46178" not in out   # antes del fix, la clave era el string del serial


# ───────────────────────── Foto → categoría (procesar_foto, Vision mockeada) ─────────────────────────

class _ContenidoFalso:
    def __init__(self, text):
        self.text = text


class _RespuestaFalsa:
    def __init__(self, text):
        self.content = [_ContenidoFalso(text)]


def _mock_vision(monkeypatch, texto_json: str):
    """Reemplaza la llamada real a Claude Vision por una respuesta fija, y el buffer de
    Supabase por uno en memoria (sin reglas de comercio, sin red)."""
    async def _create_falso(**kwargs):
        return _RespuestaFalsa(texto_json)

    guardado = {}

    async def _buffer_agregar_falso(tx):
        guardado.update(tx)
        return True

    async def _get_comercios_falso():
        return []

    monkeypatch.setattr(finanzas._anthropic.messages, "create", _create_falso)
    monkeypatch.setattr(finanzas.memory, "buffer_agregar", _buffer_agregar_falso)
    monkeypatch.setattr(finanzas.memory, "get_comercios", _get_comercios_falso)
    return guardado


def test_procesar_foto_deriva_categoria_del_primer_item(monkeypatch):
    # Boleta de Jumbo: Vision devuelve dos ítems con categorías distintas (arroz/bebida) →
    # la categoría de la transacción es la del primer ítem (Alimentación), no "Otros".
    texto = """{"tipo": "Gasto", "comercio": "JUMBO MAIPU", "fecha": "2026-06-20", "total": 2790,
    "items": [{"item": "arroz", "cantidad": 1, "precio": 1290, "categoria": "Alimentación"},
              {"item": "coca cola", "cantidad": 1, "precio": 1500, "categoria": "Bebidas"}]}"""
    guardado = _mock_vision(monkeypatch, texto)
    tx = asyncio.run(finanzas.procesar_foto(b"fake-bytes"))
    assert tx["categoria"] == "Alimentación"
    assert tx["comercio"] == "JUMBO MAIPU" and tx["monto"] == 2790
    assert [i["item"] for i in tx["items"]] == ["arroz", "coca cola"]
    assert guardado["categoria"] == "Alimentación"       # lo que de verdad se bufferizó


def test_procesar_foto_sin_items_usa_la_categoria_del_total(monkeypatch):
    # Boleta sin productos legibles (solo el monto) → Vision no manda items, cae a la
    # categoría del total tal como la haya estimado el modelo.
    texto = '{"tipo": "Gasto", "comercio": "COPEC", "fecha": "2026-06-20", "total": 15000, "categoria": "Transporte", "items": []}'
    _mock_vision(monkeypatch, texto)
    tx = asyncio.run(finanzas.procesar_foto(b"fake-bytes"))
    assert tx["categoria"] == "Transporte"
    assert tx["items"] is None


def test_procesar_foto_item_sin_categoria_la_infiere_por_nombre(monkeypatch):
    # Si Vision manda un ítem sin categoría, _linea_detalle la infiere por el nombre
    # (mismo mapa de palabras clave que usan los correos), no queda en blanco.
    texto = """{"tipo": "Gasto", "comercio": "ALMACEN LOCAL", "fecha": "2026-06-20", "total": 1500,
    "items": [{"item": "pizza uber eats", "precio": 1500}]}"""
    guardado = _mock_vision(monkeypatch, texto)
    tx = asyncio.run(finanzas.procesar_foto(b"fake-bytes"))
    assert tx["categoria"] == "Chanchería"


# ───────────────────────── Utilidades base ─────────────────────────

def test_num_parsea_formato_chileno():
    assert finanzas._num("$2.028.091") == 2028091
    assert finanzas._num("1.500,50") == 1500.50
    assert finanzas._num("") == 0.0


def test_id_unico_estable():
    a = finanzas._id_unico("2026-06-20", 15000, "Jumbo Maipú")
    b = finanzas._id_unico("2026-06-20", 15000, "Jumbo Maipú")
    assert a == b                                   # mismo gasto → mismo id (anti-duplicado)


# ───────────────────────── Parsers deterministas por banco (sin LLM) ─────────────────────────
# Fixtures = formato real de los correos de Nico (normalizados a una línea, como los entrega
# core/email_gmail). El RUT del dueño es 20255435-0.

RUT = "20255435-0"
FROM_BCH = "Banco de Chile <enviodigital@bancochile.cl>"
FROM_BCH_TEF = "serviciodetransferencias@bancochile.cl"
FROM_MACH = "MACHBANK <contacto@mail.machbank.cl>"

BCH_CARGO = ("Nicolas Emilio Castro Cordova: Te informamos que se ha realizado una compra por "
             "$12.520 con cargo a Cuenta ****5502 en STA ISABEL LOMAS el 20/06/2026 13:16. Revisa Saldos")
BCH_TEF_INTERNA = ("Comprobante de Transferencia a terceros Estimado(a): Nicolas Emilio Castro siguiente detalle: "
                   "Origen Tipo de Cuenta Cuenta Corriente Nº de Cuenta 00-448-02155-02 Destino Nombre y Apellido "
                   "Nicolas Castro Rut 20255435-0 Tipo de Cuenta Cuenta Vista Nº de Cuenta 77-702-02554-35 Banco "
                   "Banco BCI/MACHBANK Email Monto $30.000 Mensaje Fecha y Hora: sábado 20 de junio de 2026 11:06 Transacción TEF123")
BCH_TEF_TERCERO = BCH_TEF_INTERNA.replace("Nicolas Castro Rut 20255435-0", "Patricio Araneda Rut 12524337-1").replace("$30.000", "$20.000")
MACH_CREDITO = ("MACH Comprobante de compra con tu Tarjeta de Crédito MACHBANK Detalle Comercio PAYU *UBER EATS "
                "Monto pagado $1.131 Cantidad de cuotas 0 Tipo de tarjeta de crédito Virtual Últimos 4 dígitos de "
                "la tarjeta 7160 Fecha y hora 19/06/2026 - 23:00 Nr. identificador de la compra FzkQIhOj")
MACH_DEBITO = ("Comprobante de pago Detalle Comercio PUNTO CLAVE Monto (moneda original) $ 2.000 CLP Monto CLP $ 2.000 "
               "Tarjeta Visa Débito Últimos 4 dígitos de la tarjeta 1969 Nombre en tarjeta NICOLÁS EMILIO CASTRO CÓRDOVA "
               "Fecha y hora 18-06-2026 23:49 Identificador Visa 586170101458039")


def test_bch_cargo():
    d = finanzas._parsear_determinista(FROM_BCH, "Cargo en Cuenta", BCH_CARGO, RUT)
    assert d["tipo"] == "Gasto"
    assert d["monto"] == 12520
    assert d["comercio"] == "STA ISABEL LOMAS"
    assert d["categoria"] == "Alimentación"
    # El correo dice 'con cargo a Cuenta ****5502' = débito. Antes se tiraba ese dato y los tres
    # casos (cuenta / tarjeta de crédito / tarjeta de débito) salían como 'Banco de Chile' pelado.
    assert d["medio"] == "Banco de Chile débito"
    assert finanzas.normalizar_medio(d["medio"], d["subcategoria"]) == "BCh débito"
    assert d["fecha"] == "2026-06-20"
    assert d["subcategoria"] == "****5502"


def test_bch_transferencia_interna_se_registra_pero_no_es_gasto():
    """Ola 3 (D1): el traspaso propio ya NO se descarta en silencio — se registra con
    Tipo=Transferencia para que el movimiento sea visible, y el Dashboard (que filtra por
    Tipo="Gasto") lo deja fuera del conteo solo."""
    d = finanzas._parsear_determinista(FROM_BCH_TEF, "Transferencia a Terceros", BCH_TEF_INTERNA, RUT)
    assert d["_interno"] is True            # mismo RUT → entre cuentas propias
    assert d["tipo"] == "Transferencia"     # ...pero NO es gasto
    assert d["categoria"] == "Transferencias"
    assert d["monto"] == 30000


def test_bch_transferencia_a_tercero_es_gasto():
    d = finanzas._parsear_determinista(FROM_BCH_TEF, "Transferencia a Terceros", BCH_TEF_TERCERO, RUT)
    assert not d.get("_interno")
    assert d["tipo"] == "Gasto"
    assert d["monto"] == 20000
    assert d["comercio"] == "Patricio Araneda"
    assert "12524337-1" in d["subcategoria"]


def test_transferencia_interna_sin_ninguna_senal_no_la_marca(monkeypatch):
    """Sin RUT Y sin DUENO_NOMBRES configurado, Donna no tiene ninguna señal → la trata como
    gasto (se corrige en el digest). Desde que DUENO_NOMBRES existe (Ola 3), el nombre solo ya
    basta para reconocerla aunque falte el RUT — por eso este test limpia también el nombre; si
    solo se quitara el RUT, el nombre igual la reconocería (ver el test siguiente)."""
    monkeypatch.setattr(finanzas, "_dueno_nombres", lambda: [])
    d = finanzas._parsear_determinista(FROM_BCH_TEF, "Transferencia a Terceros", BCH_TEF_INTERNA, "")
    assert not d.get("_interno")


def test_transferencia_interna_el_nombre_solo_ya_basta(monkeypatch):
    """Con DUENO_NOMBRES configurado (caso real desde la Ola 3), el nombre reconoce la
    transferencia interna aunque no se pase el RUT — BCh manda ambos en el mismo correo."""
    monkeypatch.setattr(finanzas, "_dueno_nombres", lambda: ["Nicolas Castro"])
    d = finanzas._parsear_determinista(FROM_BCH_TEF, "Transferencia a Terceros", BCH_TEF_INTERNA, "")
    assert d.get("_interno") is True


# ── Ola 3 · D1/D12: la regla del RUT propio ──
# Un movimiento entre cuentas de Nico no es gasto NI ingreso: es traslado. Mach no manda RUT en
# sus avisos, solo el nombre — por eso los 5 traspasos entraron como Gasto e inflaron julio en
# $40.500 hasta la auditoría del 2026-07-23.

def test_contraparte_propia_por_rut():
    assert finanzas.es_contraparte_propia("Quien Sea", "12.345.678-9", "12345678-9")
    assert not finanzas.es_contraparte_propia("Otro", "9.876.543-2", "12345678-9")


def test_contraparte_propia_por_nombre_cuando_no_hay_rut():
    """El caso Mach: sin RUT, hay que reconocerlo por nombre (con o sin tilde)."""
    propios = ["Nicolas Castro"]
    assert finanzas.es_contraparte_propia("Nicolás  Castro", "", "", propios)
    assert finanzas.es_contraparte_propia("nicolas castro", "", "", propios)
    assert not finanzas.es_contraparte_propia("Maria Baez", "", "", propios)


def test_contraparte_propia_sin_config_no_adivina():
    """Sin RUT ni nombres configurados no puede saberlo → lo trata como tercero (gasto)."""
    assert not finanzas.es_contraparte_propia("Nicolas Castro", "", "", [])


# ── Ola 5 · F5.7: el nombre viene envuelto en la glosa del banco y con 2º nombre ──
# Con igualdad EXACTA (como era hasta este fix), "Nicolas Emilio Castro" no matchea contra
# "Nicolas Castro" — y eso es exactamente lo que traen las cartolas reales de BCh y Mach
# ("Transferencia de Nicolas Emilio Castro", "TRASPASO DE: NICOLAS EMILIO CASTRO INTERNET").
# Sin este fix, esas 3 transferencias propias se habrían colado como ingreso de un tercero.

def test_contraparte_propia_con_glosa_del_banco_y_segundo_nombre():
    propios = ["Nicolas Castro"]
    assert finanzas.es_contraparte_propia("Transferencia de Nicolas Emilio Castro", "", "", propios)
    assert finanzas.es_contraparte_propia("TRASPASO DE: NICOLAS EMILIO CASTRO INTERNET", "", "", propios)


def test_contraparte_propia_con_conector_pegado_al_nombre():
    """El formato REAL de la cartola pega el conector: 'TRASPASO A:Nicolas Castro' (sin espacio tras
    los dos puntos). Sin separar la puntuación, el token queda 'a:nicolas' y NO matchea — así se
    colaban ~15 traspasos propios como gasto y ~5 como ingreso (encontrado 2026-07-23)."""
    propios = ["Nicolas Castro"]
    assert finanzas.es_contraparte_propia("TRASPASO A:Nicolas Castro INTERNET", "", "", propios)
    assert finanzas.es_contraparte_propia("TRASPASO DE:NICOLAS EMILIO CASTRO INTERNET", "", "", propios)


def test_contraparte_propia_no_matchea_por_una_sola_palabra():
    """Exige nombre Y apellido — un tercero que comparte solo el primer nombre no debe colarse."""
    propios = ["Nicolas Castro"]
    assert not finanzas.es_contraparte_propia("Transferencia de Nicolas Castillo", "", "", propios)
    assert not finanzas.es_contraparte_propia("TRASPASO DE: Silvana Alejandra Cord INTERNET", "", "", propios)


def test_traspaso_propio_no_deja_linea_de_detalle(_cat_real):
    """Un traspaso no es una compra. Si dejara línea, sumaría en el gasto por categoría: el
    SUMIFS de Compras_Detalle no puede filtrar por Tipo, que vive en Transacciones."""
    p = {"fecha": "2026-07-05", "comercio": "Nicolas Castro", "id_unico": "ID4",
         "fuente": "correo", "monto": 7000, "tipo": "Transferencia"}
    assert asyncio.run(finanzas._filas_detalle(p, [], "Transferencias")) == []
    p["tipo"] = "Gasto"
    assert len(asyncio.run(finanzas._filas_detalle(p, [], "Transferencias"))) == 1


def test_mach_credito():
    d = finanzas._parsear_determinista(FROM_MACH, "Has hecho una compra", MACH_CREDITO, RUT)
    assert d["monto"] == 1131
    assert d["comercio"] == "PAYU *UBER EATS"
    assert d["categoria"] == "Chanchería"     # Uber Eats → delivery
    assert d["medio"] == "Mach crédito"
    assert d["fecha"] == "2026-06-19"
    assert d["subcategoria"] == "****7160"


def test_mach_debito():
    d = finanzas._parsear_determinista(FROM_MACH, "Tu compra con MACHBANK", MACH_DEBITO, RUT)
    assert d["monto"] == 2000
    assert d["comercio"] == "PUNTO CLAVE"
    assert d["medio"] == "Mach débito"
    assert d["fecha"] == "2026-06-18"
    assert d["subcategoria"] == "****1969"


def test_remitente_desconocido_cae_al_llm():
    # Copec/MercadoPago/otros no tienen parser determinista → None (el caller usa el LLM).
    assert finanzas._parsear_determinista("noreply@copec.cl", "Carga", "algo", RUT) is None


BCH_CREDITO_USD = ("Nicolas Emilio Castro Cordova: Te informamos que se ha realizado una compra por US$10,00 con "
                   "Tarjeta de Crédito ****9371 en VOYAGE AI +16098158888 US el 16/06/2026 12:23. Revisa Saldos")
BCH_CREDITO_CLP = ("Nicolas Emilio Castro Cordova: Te informamos que se ha realizado una compra por $5.990 con "
                   "Tarjeta de Crédito ****9371 en SPOTIFY el 15/06/2026 09:00. Revisa Saldos")
ITAU_RECIBIDA = ("Estimado(a) Nicolas Castro, Informamos que con fecha 20/06/2026-08:41:28, nuestro(a) cliente "
                 "MAURICIO ALEJANDRO CASTRO ACUÑA , ha instruido una transferencia de fondos con el siguiente detalle: "
                 "Banco Destino: Banco de Chile / Edwards-Citi Numero Cuenta: 004480215502 Titular Cuenta: Nicolas Castro "
                 "Monto: $150.000 Nuestro cliente ha dejado el siguiente comentario: medio julio Importante: Este email "
                 "fue generado automaticamente, por favor no responda a este mensaje.")


def test_bch_compra_credito_clp():
    d = finanzas._parsear_determinista(FROM_BCH, "Compra con Tarjeta de Crédito", BCH_CREDITO_CLP, RUT)
    assert d["tipo"] == "Gasto" and d["monto"] == 5990
    assert d["comercio"] == "SPOTIFY" and d["categoria"] == "Suscripciones"
    assert d["subcategoria"] == "****9371" and not d["dudosa"]


def test_bch_compra_usd_estima_y_marca_dudosa():
    d = finanzas._parsear_determinista(FROM_BCH, "Compra con Tarjeta de Crédito", BCH_CREDITO_USD, RUT)
    assert d["tipo"] == "Gasto"
    assert d["monto"] == round(10 * finanzas.TIPO_CAMBIO_USD)   # estimación CLP de US$10
    assert d["dudosa"] is True and "US$10,00" in d["motivo_duda"]
    assert "USD" in d["medio"] and d["fecha"] == "2026-06-16"


def test_itau_transferencia_recibida_es_ingreso():
    # Ruteo completo: remitente itau.cl → _parse_itau_recibida.
    d = finanzas._parsear_determinista("transferencias@itau.cl", "Transferencia de fondos", ITAU_RECIBIDA, RUT)
    assert d["tipo"] == "Ingreso"
    assert d["monto"] == 150000
    assert d["comercio"] == "MAURICIO ALEJANDRO CASTRO ACUÑA"
    assert d["fecha"] == "2026-06-20"
    assert d["subcategoria"] == "medio julio"


# ───────────────────────── Reglas de comercio (nombre + categoría aprendidos) ─────────────────────────

REGLAS = [{"patron": "sanva", "nombre": "negocio San Vale", "categoria": "Alimentación"}]


def test_regla_comercio_renombra_y_categoriza():
    for crudo in ("MERCADOPAGO*SANVA", "Merpago*sanvalentin"):
        n, c = finanzas._aplicar_reglas_comercio(crudo, "Otros", REGLAS)
        assert n == "negocio San Vale" and c == "Alimentación"


def test_regla_comercio_no_toca_lo_que_no_calza():
    n, c = finanzas._aplicar_reglas_comercio("STA ISABEL LOMAS", "Alimentación", REGLAS)
    assert n == "STA ISABEL LOMAS" and c == "Alimentación"


def test_regla_comercio_sin_categoria_conserva_la_actual():
    reglas = [{"patron": "uber", "nombre": "Uber", "categoria": ""}]
    n, c = finanzas._aplicar_reglas_comercio("UBER *TRIP", "Transporte", reglas)
    assert n == "Uber" and c == "Transporte"


# ───────────────────────── Validación de categoría contra Categorias (C1) ─────────────────────────
# Las 14 categorías de gasto reales + 'Transferencias' (creada por decisión de Nico 2026-07-04).
_CATS_REALES = ["Alimentación", "Chanchería", "Transporte", "Salud", "Hijo", "Entretenimiento",
                "Suscripciones", "Ropa", "Hogar", "GGCC", "Educación", "Tecnología",
                "Tarjeta Crédito", "Otro Gasto", "Transferencias"]


def _mock_categorias(monkeypatch):
    finanzas._cache_categorias = None  # el cache es global de módulo → resetear entre tests

    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [{"Categoría": c, "Tipo": "Gasto"} for c in _CATS_REALES]

    monkeypatch.setattr(finanzas.sheets, "get_dicts", _fake)


def test_categoria_de_fallback_es_otro_gasto():
    # El cajón por defecto ahora es 'Otro Gasto' (categoría real), no 'Otros' (huérfana).
    assert finanzas._categoria_de("comercio marciano xyz") == "Otro Gasto"


def test_validar_grafia_se_normaliza_a_canonica(monkeypatch):
    _mock_categorias(monkeypatch)
    assert asyncio.run(finanzas._validar_categoria("chancheria")) == ("Chanchería", True)
    assert asyncio.run(finanzas._validar_categoria("CHANCHERÍA")) == ("Chanchería", True)


def test_validar_sinonimos_conocidos(monkeypatch):
    _mock_categorias(monkeypatch)
    assert asyncio.run(finanzas._validar_categoria("Otros")) == ("Otro Gasto", True)
    assert asyncio.run(finanzas._validar_categoria("Supermercado")) == ("Alimentación", True)
    assert asyncio.run(finanzas._validar_categoria("Negocio")) == ("Alimentación", True)
    assert asyncio.run(finanzas._validar_categoria("Cosas casa")) == ("Hogar", True)
    assert asyncio.run(finanzas._validar_categoria("Software")) == ("Tecnología", True)
    assert asyncio.run(finanzas._validar_categoria("transferencia a mi mismo")) == ("Transferencias", True)


def test_validar_categoria_desconocida_cae_a_otro_gasto_e_invalida(monkeypatch):
    _mock_categorias(monkeypatch)
    cat, valida = asyncio.run(finanzas._validar_categoria("Cripto lunar"))
    assert cat == "Otro Gasto" and valida is False


def test_validar_categoria_sheets_caido_no_molesta(monkeypatch):
    finanzas._cache_categorias = None

    async def _boom(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        raise RuntimeError("Sheets down")

    monkeypatch.setattr(finanzas.sheets, "get_dicts", _boom)
    cat, valida = asyncio.run(finanzas._validar_categoria("Cualquiera"))
    assert cat == "Cualquiera" and valida is True   # sin poder validar, passthrough (no dudosa)
    finanzas._cache_categorias = None               # no contaminar otros tests


def _mock_buffer(monkeypatch):
    async def _fake_agregar(tx):
        return True

    async def _fake_comercios():
        return []

    monkeypatch.setattr(finanzas.memory, "buffer_agregar", _fake_agregar)
    monkeypatch.setattr(finanzas.memory, "get_comercios", _fake_comercios)


def test_bufferizar_categoria_huerfana_queda_dudosa(monkeypatch):
    _mock_categorias(monkeypatch)
    _mock_buffer(monkeypatch)
    tx = asyncio.run(finanzas._bufferizar(
        {"monto": 5000, "categoria": "Cosas raras", "comercio": "X", "tipo": "Gasto"}, "correo", reglas=[]))
    assert tx["categoria"] == "Otro Gasto"
    assert tx["dudosa"] is True
    assert "Cosas raras" in tx["motivo_duda"]


def test_bufferizar_categoria_valida_no_es_dudosa(monkeypatch):
    _mock_categorias(monkeypatch)
    _mock_buffer(monkeypatch)
    tx = asyncio.run(finanzas._bufferizar(
        {"monto": 5000, "categoria": "Alimentación", "comercio": "Jumbo", "tipo": "Gasto"}, "correo", reglas=[]))
    assert tx["categoria"] == "Alimentación"
    assert tx["dudosa"] is False


# ───────────────────────── Montos en palabras/slang (captura sin monto legible) ─────────────────────────

def test_num_es_digitos_y_formato():
    assert finanzas._num_es("1290") == 1290
    assert finanzas._num_es("$1.290") == 1290
    assert finanzas._num_es("gasté 5000 en uber") == 5000
    assert finanzas._num_es(2500) == 2500          # numérico pasa directo
    assert finanzas._num_es("") == 0               # nada → 0


def test_num_es_slang_chileno():
    assert finanzas._num_es("3 lucas") == 3000
    assert finanzas._num_es("dos lucas") == 2000
    assert finanzas._num_es("medio palo") == 500000
    assert finanzas._num_es("un palo") == 1_000_000


def test_num_es_palabras():
    assert finanzas._num_es("mil pesos") == 1000
    assert finanzas._num_es("dos mil quinientos") == 2500
    assert finanzas._num_es("una compota que costó mil pesos") == 1000   # ignora el ruido, agarra el número
    assert finanzas._num_es("un millón quinientos mil") == 1_500_000


def test_palabras_a_numero_none_si_no_hay():
    assert finanzas._palabras_a_numero("hola cómo estás") is None


# ───────────────────────── Gasto sin monto: no se pierde, queda esperando ─────────────────────────

def test_completar_gasto_incompleto_registra_con_el_monto(monkeypatch):
    finanzas.limpiar_gasto_incompleto()
    _mock_buffer(monkeypatch)
    # Simula el estado que deja _t_registrar_gasto cuando Nico no dio monto.
    finanzas._gasto_incompleto = {"tipo": "Gasto", "categoria": "Chanchería", "comercio": "super ganga", "medio": ""}
    r = asyncio.run(finanzas.completar_gasto_incompleto("fueron tres lucas"))
    assert r is not None and "$3.000" in r
    assert finanzas.hay_gasto_incompleto() is False       # se resolvió → estado limpio


def test_completar_gasto_incompleto_ignora_si_no_hay_monto():
    finanzas.limpiar_gasto_incompleto()
    finanzas._gasto_incompleto = {"tipo": "Gasto", "categoria": "Otros", "comercio": "", "medio": ""}
    r = asyncio.run(finanzas.completar_gasto_incompleto("no sé, después te digo"))
    assert r is None                                      # no era el monto → main.py limpia y sigue
    finanzas.limpiar_gasto_incompleto()


def test_completar_sin_estado_devuelve_none():
    finanzas.limpiar_gasto_incompleto()
    assert asyncio.run(finanzas.completar_gasto_incompleto("3000")) is None


def test_registrar_gasto_sin_monto_deja_estado_pendiente(monkeypatch):
    finanzas.limpiar_gasto_incompleto()
    r = asyncio.run(finanzas._t_registrar_gasto({"comercio": "super ganga", "categoria": "Chanchería"}))
    assert "cuánto" in r.lower()
    assert finanzas.hay_gasto_incompleto() is True        # quedó esperando el monto
    finanzas.limpiar_gasto_incompleto()


def test_registrar_gasto_con_monto_en_palabras(monkeypatch):
    finanzas.limpiar_gasto_incompleto()
    _mock_buffer(monkeypatch)
    r = asyncio.run(finanzas._t_registrar_gasto({"monto": "mil", "comercio": "kiosco"}))
    assert "$1.000" in r
    assert finanzas.hay_gasto_incompleto() is False


# ───────────────────────── parece_monto: no cualquier dígito es el monto (Tanda 1, punto 7) ─────────────────────────

def test_parece_monto_acepta_respuestas_de_plata():
    assert finanzas.parece_monto("3 lucas")
    assert finanzas.parece_monto("$1.290")
    assert finanzas.parece_monto("1290")
    assert finanzas.parece_monto("fueron tres lucas")
    assert finanzas.parece_monto("eran como 10500")


def test_parece_monto_rechaza_mensajes_de_otra_cosa_con_numeros():
    # Estos son justo los casos del audit: un dígito suelto en un mensaje que no es la respuesta.
    assert not finanzas.parece_monto("recuérdame pagar el agua el 15")
    assert not finanzas.parece_monto("dormí 7 horas")
    assert not finanzas.parece_monto("mañana tengo reunión a las 10")
    assert not finanzas.parece_monto("¿cuánto llevo gastado?")
    assert not finanzas.parece_monto("")


def test_completar_gasto_incompleto_rechaza_por_no_parecer_monto():
    finanzas.limpiar_gasto_incompleto()
    finanzas._gasto_incompleto = {"tipo": "Gasto", "categoria": "Otros", "comercio": "", "medio": "",
                                  "creado": time.time()}
    r = asyncio.run(finanzas.completar_gasto_incompleto("recuérdame pagar el agua el 15"))
    assert r is None                                      # no se traga el recordatorio como monto
    assert finanzas.hay_gasto_incompleto() is True         # el estado sigue vivo, esperando el monto real
    finanzas.limpiar_gasto_incompleto()


# ───────────────────────── Cancelación y expiración (Tanda 1, puntos 6 y 7) ─────────────────────────

def test_completar_gasto_incompleto_se_puede_cancelar():
    finanzas.limpiar_gasto_incompleto()
    finanzas._gasto_incompleto = {"tipo": "Gasto", "categoria": "Otros", "comercio": "super ganga", "medio": "",
                                  "creado": time.time()}
    r = asyncio.run(finanzas.completar_gasto_incompleto("cancelar"))
    assert r is not None and "no anoto" in r.lower()
    assert finanzas.hay_gasto_incompleto() is False


def test_gasto_incompleto_expira_solo():
    finanzas.limpiar_gasto_incompleto()
    viejo = time.time() - finanzas.TTL_GASTO_INCOMPLETO - 1
    finanzas._gasto_incompleto = {"tipo": "Gasto", "categoria": "Otros", "comercio": "", "medio": "",
                                  "creado": viejo}
    assert finanzas.hay_gasto_incompleto() is False        # ya se enfrió, no insiste con esto
    finanzas.limpiar_gasto_incompleto()
