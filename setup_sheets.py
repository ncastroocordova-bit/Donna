"""Asegura los tabs/headers canónicos del workbook único "Donna" (Plan E0).

Canon v7.2: vida + finanzas viven en UNA sola planilla. Este script es idempotente
y ADITIVO: crea los tabs que falten y agrega al final las columnas que falten,
**nunca reordena ni borra** columnas existentes (no pierde datos). Los tabs con
fórmulas (Dashboard, Comparativo, 'Tarjetas y Deuda') NO se tocan: Donna solo los
lee por celda.

Correr: python setup_sheets.py
"""
from config import settings
from core import sheets

# Headers sin acentos/emojis: el código los usa como claves de dict (get_dicts).
# El orden de esta lista solo aplica a tabs NUEVOS. En tabs existentes se respeta
# el orden ya escrito y solo se agregan al final las columnas que falten.
TABS = {
    # --- Vida ---
    # Headers EXACTOS del canon (con tildes/símbolos — calzan con Donna_Canonico.xlsx fila 2 y
    # con modules/salud.py COLS, verificado contra la planilla real 2026-07-01). Salud v2 (E8)
    # agrega las últimas 5 al final (merge aditivo). "MITs de mañana" queda como columna legado
    # sin uso (el backlog de MITs ahora vive en Tareas, Tipo=MIT) — no se borra de la planilla,
    # solo ya no la escribe el código. "MITs cumplidos" (agregada y luego retirada en la misma
    # semana) puede seguir existiendo vacía en la planilla real; este script no la vuelve a pedir.
    "Diario": ["Fecha", "Ejercicio", "Meditación", "Última comida", "Sueño 7h+", "Ánimo (1-4)",
               "Hora dormí", "MITs de mañana", "Brief ✓", "Cierre ✓", "Excepción", "Notas",
               "Primera comida", "Hora desperté", "Agua", "Proteína", "Peso (kg)"],
    # Headers EXACTOS de la planilla real (no del schema legacy "escalera" que se planeó en
    # Plan_Construccion_v7 E1 — esa fase nunca se construyó así). OJO: modules/recordatorios.py
    # hoy lee columnas que NO existen en esta lista (Dia_Fecha, Monto_Aprox, Ultimo_Aviso) —
    # es un bug del módulo, no de este script; no se toca acá (Recordatorios no es el módulo
    # en curso). Este script solo asegura que el TAB calce con lo que ya existe.
    "Recordatorios": ["Recordatorio", "Tipo", "Día / Fecha", "Monto aprox", "Estado",
                      "Posposiciones", "Última acción", "Activo"],
    # Headers EXACTOS de la planilla real.
    "Reconciliacion": ["Fecha", "Bloque / Evento", "Frente", "Min planeados", "¿Hecho?", "Delta",
                       "Min reales", "Notas"],
    # Rachas + tiempo por frente + factor de optimismo (lo genera Donna el domingo). Headers
    # EXACTOS del canon (Donna_Canonico.xlsx fila 2). Salud v2 (E8) agrega las últimas 4 al final.
    "Semanal": ["Semana (lunes)", "Cierres /7", "Briefs /7", "🏃 /7", "🧘 /7", "😴 /7", "Ayuno /7",
                "Ánimo prom", "Gasto semana", "h Tesis", "h Noomi", "h Delivery", "h Hijo",
                "Factor optimismo", "Meta semana", "¿Cumplida?", "👶 Tiempo hijo",
                "Score hábitos", "Ventana comida", "Ventana sueño", "Peso"],
    # El tab real se llama "⚙️ Config" (con el emoji) — igual que "Tarjetas y Deuda", es un
    # nombre con espacio/símbolos, por eso la clave lleva el emoji también. Nada en el código
    # lee este tab todavía (es informativo); no se re-siembra si ya tiene filas.
    "⚙️ Config": ["Parámetro", "Valor", "Nota"],
    # Headers EXACTOS de la planilla real. OJO: modules/proyectos.py hoy lee columnas que NO
    # existen acá (ID_Proy, Fase, Num, Sem_Inicio, Sem_Fin) — bug del módulo (schema "legacy"
    # de fases), no de este script. Productividad no es el módulo en curso; no se toca.
    "Tareas": ["Creada", "Descripción", "Proyecto", "Tipo", "Fecha objetivo", "Estado",
               "Completada", "Notas"],
    # Headers EXACTOS de la planilla real. OJO: modules/proyectos.py hoy lee "ID" — esa columna
    # no existe acá. Mismo bug de arriba, mismo motivo para no tocarlo ahora.
    "Proyectos": ["Proyecto", "Estado", "Foco actual", "Próxima acción", "% Avance",
                  "Última act.", "Notas"],
    "Ideas": ["Fecha", "Idea", "Estado"],
    # Lista del súper (módulo Compras, Fase 1). Estado = pendiente|comprado; lo escribe
    # modules/compras.py. La predicción de reposición (Fase 2) es diferida y no usa este tab aún.
    "Compras": ["Item", "Estado", "Fecha_Agregado", "Fecha_Comprado", "Categoria"],
    # --- Finanzas (tabs de ENTRADA; las de fórmulas no se tocan) ---
    # Headers EXACTOS de la planilla real. Intención (v2): se infiere y se confirma en el digest.
    "Transacciones": ["Fecha", "Tipo", "Categoría", "Subcategoría", "Comercio", "Monto",
                      "Medio", "Fuente", "ID_Único", "Intención"],
    "Categorias": ["Categoría", "Tipo", "Presupuesto Mensual", "Notas"],
    # NUEVO (v2): metas financieras con progreso. Sin input diario; Nico fija el Objetivo
    # y Donna actualiza Actual/Progreso cuando reporta un aporte (fin_aportar_meta). No existe
    # todavía en la planilla real — este script la crea.
    "Metas": ["Meta", "Objetivo", "Actual", "Progreso", "Notas"],
    # Detalle de compra ítem-a-ítem (v3). Una transacción de Transacciones puede tener N líneas
    # acá (ID_Tx = ID_Único del padre). Headers EXACTOS de la planilla real.
    "Compras_Detalle": ["Fecha", "Comercio", "Item", "Cantidad", "Precio", "Categoría",
                        "Intención", "Predecible", "ID_Tx", "Fuente"],
    # Historial mes a mes de deuda (Finanzas v4). Una fila por (Mes, Banco, Producto); lo escribe
    # modules/estados_cuenta.py al leer los estados de cuenta del banco. Registro visible.
    "Deuda_Mensual": ["Mes", "Banco", "Producto", "Deuda", "Cupo", "Interés mes", "Pago mínimo",
                      "Fecha estado", "Actualizado"],
}

# Filas seed de Config (solo se escriben si el tab queda SIN filas de datos). Estado
# de módulos del canon: Aprendizaje ON, Proactividad ON, Tiempo log OFF, Outlook OFF.
CONFIG_SEED = [
    ["hora_brief", "08:00", "Hora del brief de lectura"],
    ["hora_cierre", "22:00", "Hora del cierre (panel + digest)"],
    ["meta_hora_dormir", "23:00", "La linea madre del cierre"],
    ["modulo_finanzas", "ON", "Modulo 1: gastos + faro de deuda + digest (en construccion)"],
    ["modulo_aprendizaje", "ON", "Factor de optimismo / inferencias"],
    ["modulo_proactividad", "ON", "Toque proactivo 12:00 (max 1/dia)"],
    ["modulo_tiempo", "OFF", "Log de tiempo diario (dormido)"],
    ["correo_outlook", "OFF", "Fuente Outlook (no se usa)"],
]


def _ensure(sheet_id: str, tabs: dict, config_seed: list) -> None:
    if not sheet_id:
        print("  Sin id de planilla configurado; salto.")
        return
    svc = sheets._svc()
    ss = svc.spreadsheets()
    meta = ss.get(spreadsheetId=sheet_id).execute()
    existentes = {s["properties"]["title"] for s in meta["sheets"]}
    print(f"  Tabs existentes: {sorted(existentes)}")

    # 1) Crear los tabs que falten.
    add = [{"addSheet": {"properties": {"title": n}}} for n in tabs if n not in existentes]
    if add:
        ss.batchUpdate(spreadsheetId=sheet_id, body={"requests": add}).execute()
        print(f"  Tabs creados: {[r['addSheet']['properties']['title'] for r in add]}")

    # 2) Merge ADITIVO de headers: TODAS las hojas canónicas traen un banner de 1 celda en la
    # fila 1 y los headers reales viven en la fila 2 (ver Donna_Canonico.xlsx). Localiza esa fila
    # real con la misma heurística que ya usa `core.sheets._fila_headers` en runtime (≥2 celdas no
    # vacías) — así funciona igual si algún tab no trae banner. Antes esto leía siempre "1:1" (el
    # banner) y habría duplicado los 12+ headers de cada tab en la fila 1 de una planilla real.
    for nombre, canon in tabs.items():
        r = ss.values().get(spreadsheetId=sheet_id, range=sheets._rng(nombre, "A1:ZZ5")).execute()
        filas = r.get("values", [])
        h_idx, headers_row = sheets._fila_headers(filas)
        actual = [str(h).strip() for h in headers_row]
        faltan = [c for c in canon if c not in actual]
        if h_idx < 0:
            merged, fila_destino, nota = list(canon), 1, f"header nuevo {canon}"
        elif faltan:
            merged, fila_destino, nota = actual + faltan, h_idx + 1, f"+{faltan}"
        else:
            print(f"  [{nombre}] ok (sin cambios)")
            continue
        ss.values().update(
            spreadsheetId=sheet_id, range=sheets._rng(nombre, f"A{fila_destino}"),
            valueInputOption="RAW", body={"values": [merged]},
        ).execute()
        print(f"  [{nombre}] fila {fila_destino}: {nota}")

    # 3) Seed de Config solo si el tab no tiene ninguna fila de DATOS (banner + header no cuentan).
    r = ss.values().get(spreadsheetId=sheet_id, range=sheets._rng("⚙️ Config", "A1:ZZ50")).execute()
    filas = r.get("values", [])
    h_idx, _ = sheets._fila_headers(filas)
    tiene_datos = h_idx >= 0 and len(filas) > h_idx + 1
    if not tiene_datos:
        ss.values().append(
            spreadsheetId=sheet_id, range=sheets._rng("⚙️ Config", "A:C"),
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": config_seed},
        ).execute()
        print(f"  [Config] seed escrito: {len(config_seed)} filas")
    else:
        print(f"  [Config] ya tiene {len(filas) - h_idx - 1} fila(s); no se re-siembra.")


def main():
    sheet_id = settings.google_sheet_id or settings.sheet_vida
    print("Asegurando tabs canónicos del workbook único Donna (E0)...")
    if not settings.google_sheet_id:
        print("  ⚠ GOOGLE_SHEET_ID vacío; usando el id legacy de Vida. Para el workbook")
        print("    único, setea GOOGLE_SHEET_ID en .env (vida + finanzas en una planilla).")
    _ensure(sheet_id, TABS, CONFIG_SEED)
    print("\nListo. (Dashboard/Comparativo/'Tarjetas y Deuda' no se tocaron: son fórmulas.)")


if __name__ == "__main__":
    main()
