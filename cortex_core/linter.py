"""
Lint del vault: la mitad "revisar y checkear estado" del loop.
Detecta cinco tipos de problemas, ordenados por gravedad:
  1. enlaces_rotos        — wikilinks que apuntan a notas inexistentes
  2. frontmatter_invalido — campos obligatorios faltantes o valores fuera de esquema
  3. huerfanas            — notas sin ningún enlace entrante ni saliente
  4. obsoletas            — proyectos activos sin actualizar hace N días
  5. inbox_pendiente      — notas estancadas en 00-Inbox
Devuelve un dict estructurado que consumen health.py, el MCP y el loop nocturno.
"""
from __future__ import annotations

from datetime import date

from . import config, vault
from .vault import _como_fecha, _normalizar


def revisar() -> dict:
    rutas = vault.listar_notas()
    notas = [vault.cargar(r) for r in rutas]

    # Índice de títulos y nombres de archivo existentes (normalizados).
    existentes: set[str] = set()
    for n in notas:
        existentes.add(_normalizar(n.ruta.stem))
        existentes.add(_normalizar(n.titulo))

    enlaces_rotos: list[dict] = []
    frontmatter_invalido: list[dict] = []
    obsoletas: list[dict] = []
    inbox_pendiente: list[dict] = []
    con_enlace_entrante: set[str] = set()
    hoy = date.today()

    for n in notas:
        # --- wikilinks
        links = n.wikilinks
        for destino in links:
            if _normalizar(destino) in existentes:
                con_enlace_entrante.add(_normalizar(destino))
            else:
                enlaces_rotos.append({"nota": n.ruta_relativa, "enlace": destino})

        # --- frontmatter
        faltantes = [c for c in config.CAMPOS_OBLIGATORIOS if not n.meta.get(c)]
        problemas = list(faltantes)
        if n.meta.get("tipo") and n.meta["tipo"] not in config.TIPOS_VALIDOS:
            problemas.append(f"tipo inválido: {n.meta['tipo']}")
        if n.meta.get("area") and n.meta["area"] not in config.AREAS_VALIDAS:
            problemas.append(f"area inválida: {n.meta['area']}")
        if problemas:
            frontmatter_invalido.append({"nota": n.ruta_relativa, "problemas": problemas})

        # --- obsolescencia (solo proyectos activos)
        act = _como_fecha(n.meta.get("actualizada"))
        if (
            n.meta.get("tipo") == "proyecto"
            and n.meta.get("estado", "activa") == "activa"
            and act is not None
            and (hoy - act).days > config.DIAS_OBSOLETA
        ):
            obsoletas.append({
                "nota": n.ruta_relativa,
                "dias_sin_actualizar": (hoy - act).days,
            })

        # --- inbox estancado
        if n.ruta_relativa.startswith("00-Inbox"):
            creada = _como_fecha(n.meta.get("creada"))
            if creada is not None and (hoy - creada).days > config.DIAS_INBOX:
                inbox_pendiente.append({
                    "nota": n.ruta_relativa,
                    "dias_en_inbox": (hoy - creada).days,
                })

    # --- huérfanas: sin salientes y sin entrantes (excluye Home e Inbox)
    huerfanas = []
    for n in notas:
        if n.ruta.stem == "Home" or n.ruta_relativa.startswith("00-Inbox"):
            continue
        sin_salientes = len(n.wikilinks) == 0
        sin_entrantes = (
            _normalizar(n.ruta.stem) not in con_enlace_entrante
            and _normalizar(n.titulo) not in con_enlace_entrante
        )
        if sin_salientes and sin_entrantes:
            huerfanas.append({"nota": n.ruta_relativa})

    return {
        "total_notas": len(notas),
        "enlaces_rotos": enlaces_rotos,
        "frontmatter_invalido": frontmatter_invalido,
        "huerfanas": huerfanas,
        "obsoletas": obsoletas,
        "inbox_pendiente": inbox_pendiente,
    }


def resumen(reporte: dict | None = None) -> str:
    r = reporte or revisar()
    return (
        f"{r['total_notas']} notas | "
        f"{len(r['enlaces_rotos'])} enlaces rotos | "
        f"{len(r['frontmatter_invalido'])} frontmatter inválidos | "
        f"{len(r['huerfanas'])} huérfanas | "
        f"{len(r['obsoletas'])} obsoletas | "
        f"{len(r['inbox_pendiente'])} estancadas en inbox"
    )
