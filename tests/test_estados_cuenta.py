"""Evals del módulo Estados de cuenta (Finanzas v4). Puros: sin red, sin PDF real, sin LLM.
Se prueban las piezas deterministas (clasificación, mapeo al faro, historial, reconciliación,
reporte); la extracción con LLM y la descarga de Gmail se validan a mano contra los PDFs reales."""
import asyncio

from modules import estados_cuenta as ec


# ───────────────────────── Clasificación banco/producto ─────────────────────────

def test_banco_por_remitente():
    assert ec._banco("Banco de Chile <enviodigital@bancochile.cl>", "Estado de Cuenta") == "bch"
    assert ec._banco("MACHBANK <contacto@mail.machbank.cl>", "Estado de cuenta") == "mach"
    assert ec._banco("alguien@gmail.com", "hola") == "otro"


def test_producto_por_asunto_y_filename():
    assert ec._producto("Estado de Cuenta Tarjeta de Crédito", "EECCTarjetaVisa.pdf") == "tarjeta_credito"
    assert ec._producto("Cartola Línea de Crédito Mensual", "Linea_de_credito_mensual.pdf") == "linea_credito"
    assert ec._producto("Cartola de Liquidación de Intereses", "LiqIntLDCPersona.pdf") == "linea_interes"
    assert ec._producto("Cartola de Liquidación de Intereses", "LiqIntSobregiroNoPactado.pdf") == "sobregiro"


# ── Ola 5 · F5.1: cartola de cuenta corriente (débito) ──
# "cartola" también aparece en el asunto de línea de crédito, por eso el check va después.

def test_producto_cartola_cuenta_corriente():
    assert ec._producto("Cartola Cuenta Corriente", "CartolaCuentaCorrienteNacionalMensual.pdf") == \
        "cartola_cuenta_corriente"
    assert ec._producto("Cartola Cuenta Corriente MACHBANK de Junio, 2026",
                        "Cartola_CtaCte_MACHBANK de junio 2026.pdf") == "cartola_cuenta_corriente"
    # una cartola de LÍNEA sigue siendo linea_credito, no cuenta corriente
    assert ec._producto("Cartola Línea de Crédito Mensual", "Linea de credito mensual.pdf") == "linea_credito"


# ───────────────────────── Mapeo al faro (celdas-input) ─────────────────────────

def _celdas(banco, producto, d):
    """(fila, col) → valor. La firma devuelve tríos desde la Ola 1 (col B inputs, col C interés)."""
    return {(f, c): v for f, c, v in ec._celdas_faro(banco, producto, d)}


def test_celdas_faro_tarjeta_bch():
    celdas = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "cupo": 1000000})
    assert celdas[(29, 1)] == 1030608 and celdas[(28, 1)] == 1000000   # B29 deuda, B28 cupo


def test_celdas_faro_mach_linea_interes():
    assert _celdas("mach", "tarjeta_credito", {"deuda_total": 298327})[(40, 1)] == 298327
    assert _celdas("bch", "linea_credito", {"deuda_total": 969031})[(44, 1)] == 969031
    assert _celdas("bch", "linea_interes", {"interes_mes": 34210})[(45, 1)] == 34210


# ── Ola 1 · F1.1: el interés del ESTADO manda sobre el cálculo tasa×rotativa ──
# Regresión del bug encontrado el 2026-07-23: Mach declaraba $5.310 de interés y el faro
# calculaba $0 (su tasa-input es 0), subreportando los intereses muertos en $6.652/mes.

def test_interes_del_estado_va_a_la_columna_c():
    mach = _celdas("mach", "tarjeta_credito", {"deuda_total": 300000, "cupo": 300000, "interes_mes": 5310})
    assert mach[(37, 2)] == 5310          # C37 = interés reportado por Mach
    assert mach[(40, 1)] == 300000        # B40 = deuda, sigue en la columna de siempre
    bch = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "interes_mes": 24388})
    assert bch[(25, 2)] == 24388          # C25 = interés reportado por BCh


def test_sin_interes_en_el_estado_no_escribe_la_celda():
    """Si el PDF no trae interés, no se pisa la celda: B25/B37 caen solos al cálculo de respaldo."""
    celdas = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "cupo": 1000000})
    assert not [k for k in celdas if k[1] == 2]


# ── Ola 1 · F1.2: de qué mes es cada cifra del faro ──

def _hist():
    return [
        {"Mes": "2026-06", "Banco": "bch", "Producto": "tarjeta_credito", "Deuda": 1030608},
        {"Mes": "2026-06", "Banco": "bch", "Producto": "linea_credito", "Deuda": 969031},
        {"Mes": "2026-07", "Banco": "bch", "Producto": "linea_interes", "Interés mes": 34210},
        {"Mes": "2026-06", "Banco": "mach", "Producto": "tarjeta_credito", "Deuda": 298327},
        {"Mes": "2026-07", "Banco": "mach", "Producto": "tarjeta_credito", "Deuda": 300000},
    ]


def test_procedencia_toma_el_mes_mas_reciente_por_producto(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-07-23")
    por = {(p["banco"], p["producto"]): p for p in ec.procedencia(_hist())}
    assert por[("mach", "tarjeta_credito")]["mes"] == "2026-07"   # gana julio sobre junio
    assert por[("mach", "tarjeta_credito")]["atrasado"] is False
    assert por[("bch", "tarjeta_credito")]["mes"] == "2026-06"
    assert por[("bch", "tarjeta_credito")]["atrasado"] is True    # el de julio aún no llega


def test_texto_procedencia_nombra_lo_que_falta(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-07-23")
    t = ec.texto_procedencia(ec.procedencia(_hist()))
    assert "BCh tarjeta de junio" in t and "Mach tarjeta de julio" in t
    assert "Aún no llega" in t and "BCh tarjeta" in t.split("Aún no llega")[1]


def test_texto_procedencia_calla_si_todo_al_dia(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-06-15")
    t = ec.texto_procedencia(ec.procedencia(_hist()[:1]))
    assert "Aún no llega" not in t


# ───────────────────────── Historial: suma por mes (excluye interés) ─────────────────────────

def test_deuda_por_mes_excluye_filas_de_interes():
    filas = [
        {"Mes": "2026-06", "Deuda": 1030608}, {"Mes": "2026-06", "Deuda": 969031},
        {"Mes": "2026-07", "Deuda": ""},   # doc de interés (deuda vacía) → no cuenta ni crea mes
    ]
    pm = ec._deuda_por_mes(filas)
    assert pm == {"2026-06": 1030608 + 969031}
    assert "2026-07" not in pm


def _mock_get_dicts(monkeypatch, filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas
    monkeypatch.setattr(ec.sheets, "get_dicts", _fake)


# ───────────────────────── Ola 5 · F5.1: clasificación determinista de movimientos ─────────────────────────
# El LLM solo extrae fecha/descripción/monto/tipo; Python decide qué es compra/cobro/abono — más
# barato y más fácil de testear sin red que pedirle al modelo que ya venga clasificando.

def test_clasificar_movimientos_compra_cobro_abono():
    movs = [
        {"descripcion": "UNIMARC BELLAVIST", "monto": 5770, "tipo": "cargo"},
        {"descripcion": "COBRO DE MANTENCIÓN MENSUAL", "monto": 5310, "tipo": "cargo"},
        {"descripcion": "INTERÉS ACUMULADO", "monto": 5310, "tipo": "cargo"},
        {"descripcion": "Sueldo julio", "monto": 900000, "tipo": "abono"},
        {"descripcion": "monto en cero, se descarta", "monto": 0, "tipo": "cargo"},
    ]
    compras, cobros, abonos, traslados = ec._clasificar_movimientos(movs)
    assert [c["descripcion"] for c in compras] == ["UNIMARC BELLAVIST"]
    assert {c["descripcion"] for c in cobros} == {"COBRO DE MANTENCIÓN MENSUAL", "INTERÉS ACUMULADO"}
    assert [a["descripcion"] for a in abonos] == ["Sueldo julio"]
    assert traslados == []   # sin es_propio, nada es traslado


def test_clasificar_movimientos_traslados_propios_con_glosa_del_banco():
    """El caso real (cartola 2026-07-23): 'TRASPASO A:/DE:' pega el conector al nombre. Con la regla
    del RUT propio activada, un traspaso entre cuentas de Nico —salga o entre plata— es traslado, ni
    gasto ni ingreso. Un traspaso a/de un TERCERO sí cuenta (gasto si sale, ingreso si entra)."""
    es_propio = ec._es_propio("", ["Nicolas Castro"])
    movs = [
        {"descripcion": "TRASPASO A:Nicolas Castro INTERNET", "monto": 70000, "tipo": "cargo"},
        {"descripcion": "TRASPASO DE:NICOLAS EMILIO CASTRO INTERNET", "monto": 35000, "tipo": "abono"},
        {"descripcion": "TRASPASO A:Patricio Araneda INTERNET", "monto": 20000, "tipo": "cargo"},
        {"descripcion": "TRASPASO DE:MAURICIO ALEJANDRO CAS INTERNET", "monto": 300000, "tipo": "abono"},
    ]
    compras, _, abonos, traslados = ec._clasificar_movimientos(movs, es_propio)
    assert {t["descripcion"] for t in traslados} == {
        "TRASPASO A:Nicolas Castro INTERNET", "TRASPASO DE:NICOLAS EMILIO CASTRO INTERNET"}
    assert [c["descripcion"] for c in compras] == ["TRASPASO A:Patricio Araneda INTERNET"]  # tercero → gasto
    assert [a["descripcion"] for a in abonos] == ["TRASPASO DE:MAURICIO ALEJANDRO CAS INTERNET"]  # tercero → ingreso


def test_diferencial_excluye_traslados_propios_de_las_faltantes():
    """Un 'TRASPASO A:Nicolas Castro' NO debe aparecer como compra faltante — no es gasto."""
    es_propio = ec._es_propio("", ["Nicolas Castro"])
    doc = _doc(movimientos=[
        {"fecha": "2026-06-01", "descripcion": "TRASPASO A:Nicolas Castro INTERNET", "monto": 70000, "tipo": "cargo"},
        {"fecha": "2026-06-05", "descripcion": "SHELL", "monto": 10000, "tipo": "cargo"},
    ])
    d = ec.diferencial(doc, [], es_propio=es_propio)
    assert [f["comercio"] for f in d["faltantes"]] == ["SHELL"]     # el traslado propio no está
    assert d["compras_total"] == 10000


def test_bucket_cobro_agrupa_por_palabra_clave():
    assert ec._bucket_cobro("INTERÉS ACUMULADO") == "interés"
    assert ec._bucket_cobro("COBRO DE MANTENCIÓN MENSUAL") == "mantención"
    assert ec._bucket_cobro("CUOTA 02/03") == "cuotas"
    assert ec._bucket_cobro("IMPUESTO DECRETO LEY 3475") == "impuestos"
    assert ec._bucket_cobro("algo raro sin palabra clave") == "otros cobros"


# ───────────────────────── Ola 5 · F5.2/F5.3: el diferencial por documento ─────────────────────────

def _doc(**kw):
    # Período ancho por defecto (para no chocar con las fechas de cada escenario); el test de
    # período específicamente angosto lo pasa explícito.
    base = {"banco": "bch", "producto": "tarjeta_credito",
           "periodo_desde": "2026-05-01", "periodo_hasta": "2026-07-31",
           "movimientos": []}
    base.update(kw)
    return base


def test_diferencial_marca_faltantes_y_separa_cobros():
    """Reemplaza al viejo test_reconciliar_*: mismo escenario, ahora contra `diferencial()`, que
    además separa los cobros del banco en vez de simplemente descartarlos."""
    doc = _doc(movimientos=[
        {"fecha": "2026-06-11", "descripcion": "UNIMARC", "monto": 5770, "tipo": "cargo"},   # ya está
        {"fecha": "2026-06-05", "descripcion": "SHELL", "monto": 10000, "tipo": "cargo"},    # falta
        {"fecha": "2026-06-13", "descripcion": "AVANCE EN CUOTAS", "monto": 40000, "tipo": "cargo"},
        {"fecha": "2026-06-01", "descripcion": "PAGO PESOS TEF", "monto": 45049, "tipo": "cargo"},
    ])
    planilla = [{"Fecha": "2026-06-11", "Monto": 5770}]
    d = ec.diferencial(doc, planilla)
    assert [f["comercio"] for f in d["faltantes"]] == ["SHELL"]
    assert d["compras_total"] == 5770 + 10000          # solo compras reales, sin el ruido
    assert d["anotado_total"] == 5770
    assert d["cobros"] == {"cuotas": 40000, "otros cobros": 45049}


def test_diferencial_respeta_el_periodo_del_documento():
    """Una compra fuera del período del estado no debe contar ni como anotada ni como faltante —
    pertenece a otro ciclo de facturación."""
    doc = _doc(periodo_desde="2026-06-18", periodo_hasta="2026-07-18",
               movimientos=[{"fecha": "2026-05-01", "descripcion": "COMPRA VIEJA", "monto": 9999,
                            "tipo": "cargo"}])
    d = ec.diferencial(doc, [])
    assert d["compras_n"] == 0 and d["faltantes"] == []


def test_diferencial_sin_periodo_cae_a_ventana_de_respaldo_y_lo_marca():
    """Si el PDF no trae período legible, usa una ventana de 45 días y lo marca `periodo_estimado`
    — nunca presenta un cuadre como exacto cuando el rango se adivinó."""
    doc = _doc(periodo_desde=None, periodo_hasta=None, fecha="2026-07-20",
               movimientos=[{"fecha": "2026-07-10", "descripcion": "X", "monto": 1000, "tipo": "cargo"}])
    d = ec.diferencial(doc, [])
    assert d["periodo_estimado"] is True
    assert d["compras_n"] == 1                          # igual encuentra la compra en la ventana


def test_diferencial_matchea_contra_fecha_serial_de_sheets():
    """Regresión del bug real encontrado el 2026-07-23: Transacciones se lee con
    UNFORMATTED_VALUE, así que `Fecha` llega como serie de Sheets (46163), no "2026-05-21". Sin
    `sheets.fecha_iso()` en `diferencial()`, esto NUNCA matcheaba — "Anotado por Donna" daba $0
    en absolutamente todos los documentos reales al validar la Ola 5."""
    doc = _doc(movimientos=[{"fecha": "2026-05-21", "descripcion": "OpenAI", "monto": 5500,
                             "tipo": "cargo"}])
    planilla = [{"Fecha": 46163, "Monto": 5500}]   # serial real, verificado contra la API de Sheets
    d = ec.diferencial(doc, planilla)
    assert d["faltantes"] == []
    assert d["anotado_total"] == 5500


def test_diferencial_cuadra_perfecto_sin_faltantes():
    doc = _doc(movimientos=[{"fecha": "2026-07-01", "descripcion": "X", "monto": 1000, "tipo": "cargo"}])
    d = ec.diferencial(doc, [{"Fecha": "2026-07-01", "Monto": 1000}])
    assert d["faltantes"] == [] and d["anotado_total"] == d["compras_total"] == 1000


def test_texto_diferencial_muestra_cuadra_o_falta():
    d = ec.diferencial(_doc(movimientos=[
        {"fecha": "2026-07-01", "descripcion": "X", "monto": 1000, "tipo": "cargo"},
    ]), [])
    t = ec.texto_diferencial(d)
    assert "Falta anotar" in t and "$1.000" in t
    ok = ec.diferencial(_doc(movimientos=[
        {"fecha": "2026-07-01", "descripcion": "X", "monto": 1000, "tipo": "cargo"},
    ]), [{"Fecha": "2026-07-01", "Monto": 1000}])
    assert "✓ cuadra" in ec.texto_diferencial(ok)


# ───────────────────────── Ola 5 · F5.5/F5.7: candidatos al buffer del digest ─────────────────────────
# No escriben a Transacciones — entran al buffer y salen en el próximo digest (mismo patrón que
# cualquier gasto de correo/foto). Se mockea `finanzas._bufferizar` para no tocar Supabase/Sheets.

def _mock_bufferizar(monkeypatch):
    llamadas = []
    async def _fake(datos, fuente, reglas=None):
        llamadas.append(datos)
        return datos
    monkeypatch.setattr(ec.finanzas, "_bufferizar", _fake)
    return llamadas


def test_registrar_faltantes_bufferiza_cada_compra(monkeypatch):
    llamadas = _mock_bufferizar(monkeypatch)
    diffs = [{"banco": "bch", "faltantes": [{"fecha": "2026-07-05", "comercio": "SHELL", "monto": 10000}]}]
    n = asyncio.run(ec._registrar_faltantes(diffs))
    assert n == 1
    assert llamadas[0]["tipo"] == "Gasto" and llamadas[0]["monto"] == 10000


def test_registrar_abonos_descarta_traspaso_propio(monkeypatch):
    """Regla del RUT propio (D12): un abono desde una cuenta de Nico es traslado, no ingreso."""
    llamadas = _mock_bufferizar(monkeypatch)
    abonos = [
        {"fecha": "2026-07-05", "descripcion": "Nicolas Castro", "monto": 50000},   # es él mismo
        {"fecha": "2026-07-06", "descripcion": "Empresa XYZ SPA", "monto": 900000}, # tercero → sí
    ]
    n = asyncio.run(ec._registrar_abonos("bch", abonos, dueno_rut=""))
    assert n == 1
    assert llamadas[0]["tipo"] == "Ingreso" and llamadas[0]["monto"] == 900000
    assert llamadas[0]["categoria"] == "Otro Ingreso"


def test_registrar_abonos_filtra_deuda_reembolso_y_ruido(monkeypatch):
    """Tres cosas que ENTRAN a la cuenta pero NO son ingreso real (contra cartolas reales 2026-07-23):
    plata de la línea de crédito (deuda), reembolsos (devuelven un gasto), y montos ínfimos (cashback)."""
    llamadas = _mock_bufferizar(monkeypatch)
    abonos = [
        {"fecha": "2026-06-01", "descripcion": "TRANSFERENCIA DESDE LINEA DE CREDI OF. BAN", "monto": 65000},
        {"fecha": "2026-06-07", "descripcion": "Reembolso compra con tarjeta virtual - GRAN ASIA", "monto": 3200},
        {"fecha": "2026-06-17", "descripcion": "Abono cashback de openai - BciPlus+", "monto": 28},
        {"fecha": "2026-06-08", "descripcion": "TRASPASO DE:MAURICIO ALEJANDRO CAS INTERNET", "monto": 150000},
    ]
    n = asyncio.run(ec._registrar_abonos("bch", abonos, dueno_rut=""))
    assert n == 1                                        # solo Mauricio (tercero, > $1.000, ingreso real)
    assert llamadas[0]["monto"] == 150000


# ───────────────────────── Ola 5 · F5.7: saldo mensual (hoja propia) ─────────────────────────

def test_upsert_saldo_no_toca_deuda_mensual(monkeypatch):
    """El saldo va a su propia hoja `Saldos` — nunca a Deuda_Mensual, o `_deuda_por_mes` lo sumaría
    junto con la deuda real."""
    escritos = []
    async def _fake_get_rows(hoja, sheet_id=None):
        assert hoja == ec.HOJA_SALDOS
        return [ec.SALDO_COLS]
    async def _fake_append(hoja, vals, sheet_id=None):
        assert hoja == ec.HOJA_SALDOS
        escritos.append(vals)
    monkeypatch.setattr(ec.sheets, "get_rows", _fake_get_rows)
    monkeypatch.setattr(ec.sheets, "append_row", _fake_append)
    asyncio.run(ec._upsert_saldo("bch", "2026-07", 450000, "2026-07-22"))
    assert escritos[0][:3] == ["2026-07", "bch", 450000]


# ───────────────────────── Reporte + progreso ─────────────────────────

def test_texto_reporte_completo():
    diff = ec.diferencial(_doc(movimientos=[
        {"fecha": "2026-06-05", "descripcion": "SHELL", "monto": 10000, "tipo": "cargo"},
    ]), [])
    r = {"nuevos": 2, "bancos": {"bch", "mach"}, "deuda_actual": 2297966, "delta": -50000,
         "registros": [{"banco": "bch", "producto": "tarjeta_credito", "deuda_total": 1030608},
                       {"banco": "bch", "producto": "linea_interes", "deuda_total": None, "interes_mes": 34210}],
         "reconciliaciones": [diff], "faltantes_agregados": 1, "ingresos_agregados": 0}
    t = ec.texto_reporte(r)
    assert "Llegaron estados" in t and "$2.297.966" in t
    assert "Bajó" in t and "$50.000" in t
    assert "interés línea $34.210" in t          # el doc de interés muestra el interés, no una deuda fantasma
    assert "Falta anotar" in t and "SHELL" not in t  # el diferencial no lista el detalle, solo el monto
    assert "quedaron en tu próximo digest" in t


def test_texto_reporte_sin_novedades_vacio():
    assert ec.texto_reporte({"nuevos": 0}) == ""


def test_progreso_deuda_lee_historial(monkeypatch):
    _mock_get_dicts(monkeypatch, [{"Mes": "2026-05", "Deuda": 2000000}, {"Mes": "2026-06", "Deuda": 2297966}])
    t = asyncio.run(ec._t_progreso({}))
    assert "2026-05" in t and "2026-06" in t
    assert "subió" in t.lower()


def test_progreso_sin_historial(monkeypatch):
    _mock_get_dicts(monkeypatch, [])
    t = asyncio.run(ec._t_progreso({}))
    assert "todavía no" in t.lower()
