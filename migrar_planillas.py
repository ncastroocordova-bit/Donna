"""Script de un solo uso: migra la config/datos reales de las dos planillas .xlsx
de Nico a la Google Sheet de Donna (que ya tiene la estructura nueva).

Lee local con openpyxl, escribe en la Sheet via la API. Mapea columnas por NOMBRE
(no por posición) para ser robusto. Correr una vez:  python migrar_planillas.py
"""
import unicodedata
from datetime import date, timedelta

import openpyxl

import sheets
from config import settings

FINANZAS = r"C:\Proyectos\Agentes Personales\Finanzas_Personales.xlsx"
VIDA = r"C:\Proyectos\Agentes Personales\vida_organizada_v5.xlsx"


def _norm(s) -> str:
    """Normaliza un header: sin acentos, sin emojis/símbolos, minúsculas."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(c for c in s if c.isalnum()).lower()


def _fmt(v):
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return v


def _leer(path, hoja):
    """Devuelve (headers_norm→idx, lista de filas de datos) detectando el header."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[hoja]
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    hr = None
    for i, row in enumerate(filas[:12]):
        if len([c for c in row if c not in (None, "")]) >= 3:
            hr = i
            break
    headers = filas[hr]
    idx = {_norm(h): j for j, h in enumerate(headers) if h not in (None, "")}
    datos = [r for r in filas[hr + 1:] if len([c for c in r if c not in (None, "")]) >= 2]
    return idx, datos


def _mapear(idx, datos, mapeo):
    """mapeo: lista de (col_destino, label_fuente_norm). Devuelve filas alineadas."""
    out = []
    for r in datos:
        fila = []
        for _, label in mapeo:
            j = idx.get(label)
            fila.append(_fmt(r[j]) if j is not None and j < len(r) else "")
        out.append(fila)
    return out


def _escribir(tab, filas):
    """Escribe las filas desde A2 (debajo del header) en un solo update."""
    if not filas:
        print(f"  {tab}: (sin datos)")
        return
    sheets._svc().spreadsheets().values().update(
        spreadsheetId=settings.google_sheet_id,
        range=f"{tab}!A2",
        valueInputOption="USER_ENTERED",
        body={"values": filas},
    ).execute()
    print(f"  {tab}: {len(filas)} filas migradas")


def migrar_categorias():
    idx, datos = _leer(FINANZAS, "Categorias")
    filas = _mapear(idx, datos, [("Categoria", "categoria"), ("Tipo", "tipo"),
                                 ("Presupuesto", "presupuestomensual"), ("Notas", "notas")])
    _escribir("Categorias", filas)


def migrar_tarjetas():
    # Matriz: concepto en col0, valores en las columnas Banco/Mach/TOTAL.
    idx, datos = _leer(FINANZAS, "Tarjetas de Crédito")
    banco = next((j for n, j in idx.items() if "banco" in n), 1)
    mach = next((j for n, j in idx.items() if "mach" in n), 2)
    total = next((j for n, j in idx.items() if "total" in n), 3)
    filas = []
    for r in datos:
        concepto = r[0]
        if concepto in (None, ""):
            continue
        filas.append([_fmt(concepto), _fmt(r[banco] if banco < len(r) else ""),
                      _fmt(r[mach] if mach < len(r) else ""), _fmt(r[total] if total < len(r) else "")])
    _escribir("Tarjetas", filas)


def migrar_presupuesto():
    idx, datos = _leer(VIDA, "📊 Presupuesto")
    filas = _mapear(idx, datos, [("Fuente", "fuente"), ("Monto", "montoestimado"),
                                 ("Tipo", "tipo"), ("Notas", "notas")])
    _escribir("Presupuesto", filas)


def migrar_proyectos():
    idx, datos = _leer(VIDA, "🚀 Proyectos")
    filas = _mapear(idx, datos, [("ID", "id"), ("Proyecto", "proyecto"), ("Descripcion", "descripcion"),
                                 ("Estado", "estado"), ("Fecha_Inicio", "fechainicio"),
                                 ("Sem_Estimadas", "semestimadas"), ("Prioridad", "prioridad"), ("Notas", "notas")])
    _escribir("Proyectos", filas)


def migrar_tareas():
    idx, datos = _leer(VIDA, "✅ Tareas")
    filas = _mapear(idx, datos, [("ID_Proy", "idproy"), ("Proyecto", "proyecto"), ("Fase", "fase"),
                                 ("Num", "tarea"), ("Descripcion", "descripciondelatarea"),
                                 ("Sem_Inicio", "seminicio"), ("Sem_Fin", "semfin"), ("Estado", "estado"),
                                 ("Prioridad", "prioridad"), ("Completada", "completada"), ("Notas", "notas")])
    # 'descripciondelatarea' puede truncarse distinto; fallback a 'descripcion'
    if all(not f[4] for f in filas):
        d = next((j for n, j in idx.items() if n.startswith("descripcion")), None)
        if d is not None:
            for f, r in zip(filas, datos):
                f[4] = _fmt(r[d]) if d < len(r) else ""
    _escribir("Tareas", filas)


def migrar_metas():
    idx, datos = _leer(VIDA, "📊 Metas Semanales")
    filas = _mapear(idx, datos, [("Semana", "semana"), ("Fechas", "fechas"),
                                 ("Dias_Tesis", "diastesis"), ("Meta_Tesis", "metatesis"),
                                 ("Dias_Delivery", "diasdelivery"), ("Meta_Delivery", "metadelivery"),
                                 ("Horas_Proy", "horasproyectos"), ("Meta_HProy", "metahproy"),
                                 ("Tareas_Noomi", "tareasnoomi"), ("Meta_Tareas", "metatareas"), ("Notas", "notas")])
    _escribir("MetasSemanales", filas)


def sembrar_habitos(anio=2026):
    """Pre-siembra la columna Fecha con todos los días del año (matriz diaria)."""
    d = date(anio, 1, 1)
    filas = []
    while d.year == anio:
        filas.append([d.strftime("%Y-%m-%d")])
        d += timedelta(days=1)
    _escribir("Habitos", filas)


def main():
    print("Migrando config/datos de las planillas a la Sheet de Donna...")
    migrar_categorias()
    migrar_tarjetas()
    migrar_presupuesto()
    migrar_proyectos()
    migrar_tareas()
    migrar_metas()
    sembrar_habitos()
    print("Migración lista.")


if __name__ == "__main__":
    main()
