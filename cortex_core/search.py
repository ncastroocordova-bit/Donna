"""
Búsqueda de texto completo sobre el vault, sin base de datos.
Puntaje simple: título > tags > cuerpo. Suficiente para vaults de
cientos de notas; si algún día se hace lento, se agrega un índice SQLite
sin cambiar la interfaz.
"""
from __future__ import annotations

import re

from . import vault
from .vault import _normalizar


def buscar(consulta: str, limite: int = 10, area: str | None = None) -> list[dict]:
    terminos = [t for t in _normalizar(consulta).split() if len(t) >= 2]
    if not terminos:
        return []

    resultados = []
    for ruta in vault.listar_notas():
        nota = vault.cargar(ruta)
        if area and nota.meta.get("area") != area:
            continue

        titulo_n = _normalizar(nota.titulo)
        tags_n = _normalizar(" ".join(str(t) for t in (nota.meta.get("tags") or [])))
        cuerpo_n = _normalizar(nota.cuerpo)

        puntaje = 0
        for t in terminos:
            if t in titulo_n:
                puntaje += 5
            if t in tags_n:
                puntaje += 3
            puntaje += min(cuerpo_n.count(t), 5)  # tope para no premiar spam

        if puntaje > 0:
            resultados.append({
                "ruta": nota.ruta_relativa,
                "titulo": nota.titulo,
                "area": nota.meta.get("area", "?"),
                "puntaje": puntaje,
                "extracto": _extracto(nota.cuerpo, terminos),
            })

    resultados.sort(key=lambda r: r["puntaje"], reverse=True)
    return resultados[:limite]


def _extracto(cuerpo: str, terminos: list[str], ancho: int = 160) -> str:
    cuerpo_plano = re.sub(r"\s+", " ", cuerpo).strip()
    cuerpo_n = _normalizar(cuerpo_plano)
    for t in terminos:
        pos = cuerpo_n.find(t)
        if pos >= 0:
            ini = max(0, pos - ancho // 3)
            return ("…" if ini else "") + cuerpo_plano[ini:ini + ancho] + "…"
    return cuerpo_plano[:ancho]
