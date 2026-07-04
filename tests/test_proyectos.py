"""Evals del Módulo 6 (Proyectos + Tareas) contra el schema REAL de la planilla:
    Proyectos: Proyecto · Estado · Foco actual · Próxima acción · % Avance · Última act. · Notas
    Tareas:    Creada · Descripción · Proyecto · Tipo · Fecha objetivo · Estado · Completada · Notas

Regresión de la auditoría 2026-07-01: el módulo asumía IDs/fases fantasma (ID_Proy, ID, Fase,
Descripcion sin tilde, Prioridad). Efectos: _avance comparaba ""=="" → todos los proyectos
mostraban TODAS las tareas; tarea_listar imprimía "None"; tarea_crear escribía 11 valores en
8 columnas; tarea_completar tiraba ValueError siempre.

Puros: sin red, sin Sheets. Se monkeypatchea la llamada a Sheets.
"""
import asyncio

from modules import proyectos

C_T = proyectos.COLS_TAREAS
C_P = proyectos.COLS_PROY


def _tarea(proyecto, desc, tipo="Tarea", estado="Pendiente", completada="", fecha=""):
    return {
        C_T["creada"]: "2026-07-01", C_T["descripcion"]: desc, C_T["proyecto"]: proyecto,
        C_T["tipo"]: tipo, C_T["fecha_objetivo"]: fecha, C_T["estado"]: estado,
        C_T["completada"]: completada, C_T["notas"]: "",
    }


def _mock_tareas(monkeypatch, filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas
    monkeypatch.setattr(proyectos.sheets, "get_dicts", _fake)


def _mock_dos_hojas(monkeypatch, proyectos_filas, tareas_filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return proyectos_filas if hoja == proyectos.HOJA_PROY else tareas_filas
    monkeypatch.setattr(proyectos.sheets, "get_dicts", _fake)


# ───────────────────────── _avance por nombre ─────────────────────────

def test_avance_cuenta_solo_las_del_proyecto(monkeypatch):
    _mock_tareas(monkeypatch, [
        _tarea("Tesis", "a", estado="Completada", completada="Sí"),
        _tarea("Tesis", "b"),
        _tarea("Noomi", "c", estado="Completada", completada="Sí"),  # de otro proyecto
    ])
    assert asyncio.run(proyectos._avance("Tesis")) == (1, 2)


def test_avance_ignora_mits(monkeypatch):
    _mock_tareas(monkeypatch, [
        _tarea("Tesis", "real"),
        _tarea("Tesis", "un MIT", tipo="MIT"),  # MIT de Salud en la misma hoja
    ])
    h, tot = asyncio.run(proyectos._avance("Tesis"))
    assert tot == 1  # el MIT no cuenta


# ───────────────────────── listado (regresión del "None") ─────────────────────────

def test_tarea_listar_muestra_descripcion_real(monkeypatch):
    _mock_tareas(monkeypatch, [_tarea("Tesis", "Escribir capítulo 2", fecha="2026-07-10")])
    txt = asyncio.run(proyectos._tarea_listar({}))
    assert "Escribir capítulo 2" in txt
    assert "None" not in txt


def test_proy_listar_avance_por_proyecto(monkeypatch):
    proys = [{C_P["proyecto"]: "Tesis", C_P["estado"]: "Activo", C_P["foco"]: "Lab"}]
    tareas = [_tarea("Tesis", "a", estado="Completada", completada="Sí"), _tarea("Tesis", "b")]
    _mock_dos_hojas(monkeypatch, proys, tareas)
    txt = asyncio.run(proyectos._proy_listar({}))
    assert "Tesis" in txt and "1/2" in txt and "foco: Lab" in txt


# ───────────────────────── escrituras con el schema real ─────────────────────────

def test_tarea_crear_appendea_8_valores(monkeypatch):
    cap = {}

    async def _fake_append(hoja, valores, sheet_id=None):
        cap["hoja"], cap["v"] = hoja, valores

    monkeypatch.setattr(proyectos.sheets, "append_row", _fake_append)
    r = asyncio.run(proyectos._tarea_crear({"descripcion": "Probar fix", "proyecto": ""}))
    v = cap["v"]
    assert cap["hoja"] == "Tareas"
    assert len(v) == 8               # 8 columnas reales, no 11
    assert v[1] == "Probar fix"      # Descripción
    assert v[5] == "Pendiente"       # Estado (no una prioridad corrida)
    assert "Probar fix" in r


def test_proy_crear_appendea_7_valores(monkeypatch):
    cap = {}

    async def _fake_append(hoja, valores, sheet_id=None):
        cap["hoja"], cap["v"] = hoja, valores

    monkeypatch.setattr(proyectos.sheets, "append_row", _fake_append)
    asyncio.run(proyectos._proy_crear({"nombre": "Nuevo Proyecto"}))
    v = cap["v"]
    assert cap["hoja"] == "Proyectos"
    assert len(v) == 7               # 7 columnas reales, no 8 con ID
    assert v[0] == "Nuevo Proyecto"  # Proyecto (no un ID)
    assert v[1] == "Activo"          # Estado
    assert v[4] == "0%"              # % Avance


def test_tarea_completar_marca_estado_y_completada(monkeypatch):
    headers = ["Creada", "Descripción", "Proyecto", "Tipo", "Fecha objetivo", "Estado", "Completada", "Notas"]
    fila = ["2026-07-01", "Escribir capítulo 2", "Tesis", "Tarea", "2026-07-10", "Pendiente", "", ""]
    filas = [["🗂️ TAREAS — banner de la hoja"], headers, fila]  # banner + headers + 1 dato

    async def _fake_get_rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas

    sets = []

    async def _fake_set_cell(hoja, f, c, valor, sheet_id=None):
        sets.append((f, c, valor))

    monkeypatch.setattr(proyectos.sheets, "get_rows", _fake_get_rows)
    monkeypatch.setattr(proyectos.sheets, "set_cell", _fake_set_cell)
    r = asyncio.run(proyectos._tarea_completar({"descripcion": "capítulo 2"}))

    # banner(fila 1) + headers(fila 2) + dato(fila 3, 1-based)
    assert (3, 5, "Completada") in sets   # Estado en la columna 5 (0-based)
    assert (3, 6, "Sí") in sets           # Completada en la columna 6
    assert "completada" in r.lower()
