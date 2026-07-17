"""
Salud del vault: convierte el lint en un puntaje 0-100 y un reporte
Markdown que queda guardado en 90-Meta/Salud/ — visible en Obsidian.
Es la métrica que el loop nocturno usa para saber si mejora o empeora.
"""
from __future__ import annotations

from datetime import date

from . import config, linter, vault

PESOS = {
    "enlaces_rotos": 4,
    "frontmatter_invalido": 3,
    "huerfanas": 2,
    "obsoletas": 2,
    "inbox_pendiente": 1,
}


def puntaje(reporte: dict | None = None) -> int:
    r = reporte or linter.revisar()
    castigo = sum(len(r[clave]) * peso for clave, peso in PESOS.items())
    return max(0, 100 - castigo)


def generar_reporte(guardar: bool = True) -> str:
    r = linter.revisar()
    p = puntaje(r)
    hoy = str(date.today())

    lineas = [
        f"# Salud del vault — {hoy}",
        "",
        f"**Puntaje: {p}/100** · {r['total_notas']} notas totales",
        "",
    ]

    secciones = [
        ("enlaces_rotos", "🔗 Enlaces rotos",
         lambda i: f"- `{i['nota']}` → [[{i['enlace']}]] no existe"),
        ("frontmatter_invalido", "📋 Frontmatter inválido",
         lambda i: f"- `{i['nota']}`: {', '.join(str(x) for x in i['problemas'])}"),
        ("huerfanas", "🏝️ Notas huérfanas (sin enlaces)",
         lambda i: f"- `{i['nota']}`"),
        ("obsoletas", "🕸️ Proyectos activos sin actualizar",
         lambda i: f"- `{i['nota']}` ({i['dias_sin_actualizar']} días)"),
        ("inbox_pendiente", "📥 Estancadas en Inbox",
         lambda i: f"- `{i['nota']}` ({i['dias_en_inbox']} días)"),
    ]

    for clave, titulo, fmt in secciones:
        items = r[clave]
        lineas.append(f"## {titulo} ({len(items)})")
        lineas.extend(fmt(i) for i in items[:25])
        if len(items) > 25:
            lineas.append(f"- … y {len(items) - 25} más")
        if not items:
            lineas.append("- Sin problemas ✅")
        lineas.append("")

    contenido = "\n".join(lineas)

    if guardar:
        carpeta = config.VAULT_PATH / "90-Meta" / "Salud"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{hoy}.md").write_text(contenido, encoding="utf-8")

    return contenido
