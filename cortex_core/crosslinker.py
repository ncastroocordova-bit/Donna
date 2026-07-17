"""
Cross-linker: la mitad "mejorar" del loop.
Detecta menciones de títulos de notas existentes que no están enlazadas
y las convierte en [[wikilinks]] — el tejido que hace crecer el grafo.

Diseño conservador a propósito:
  - solo coincidencias exactas del título (con límite de palabra)
  - ignora frontmatter, bloques de código y líneas que ya tienen el link
  - máximo 1 enlace nuevo por mención por nota (la primera aparición)
  - sugerir() nunca modifica; aplicar() modifica solo lo sugerido
"""
from __future__ import annotations

import re
from datetime import date

from . import vault


def _segmentos_editables(cuerpo: str):
    """Divide el cuerpo en (editable, texto): los bloques ``` no se tocan."""
    partes = re.split(r"(```.*?```)", cuerpo, flags=re.DOTALL)
    for parte in partes:
        yield (not parte.startswith("```"), parte)


def sugerir() -> list[dict]:
    rutas = vault.listar_notas()
    notas = [vault.cargar(r) for r in rutas]

    # Títulos candidatos: 4+ caracteres para evitar falsos positivos.
    titulos = {n.titulo: n for n in notas if len(n.titulo) >= 4}

    sugerencias = []
    for n in notas:
        ya_enlazados = {l.lower() for l in n.wikilinks}
        for titulo in titulos:
            if titulo.lower() == n.titulo.lower():
                continue  # no auto-enlazarse
            if titulo.lower() in ya_enlazados:
                continue
            patron = re.compile(
                r"(?<!\[\[)\b" + re.escape(titulo) + r"\b(?!\]\])",
                re.IGNORECASE,
            )
            encontrado = any(
                editable and patron.search(seg)
                for editable, seg in _segmentos_editables(n.cuerpo)
            )
            if encontrado:
                sugerencias.append({"nota": n.ruta_relativa, "mencion": titulo})
    return sugerencias


def aplicar(sugerencias: list[dict] | None = None, max_por_nota: int = 3) -> int:
    """Aplica las sugerencias (primera aparición por mención). Devuelve el total aplicado."""
    sugerencias = sugerencias if sugerencias is not None else sugerir()
    aplicados = 0
    por_nota: dict[str, int] = {}

    for s in sugerencias:
        if por_nota.get(s["nota"], 0) >= max_por_nota:
            continue
        nota = vault.leer_nota(s["nota"])
        if nota is None:
            continue

        patron = re.compile(
            r"(?<!\[\[)\b" + re.escape(s["mencion"]) + r"\b(?!\]\])",
            re.IGNORECASE,
        )

        nuevas_partes = []
        hecho = False
        for editable, seg in _segmentos_editables(nota.cuerpo):
            if editable and not hecho and patron.search(seg):
                seg = patron.sub(f"[[{s['mencion']}]]", seg, count=1)
                hecho = True
            nuevas_partes.append(seg)

        if hecho:
            nota.cuerpo = "".join(nuevas_partes)
            # Tejer modifica la nota: refrescar `actualizada`. PERO se
            # preserva `autor`: el tejedor no es autor del contenido, y
            # pisarlo destruiría la atribución multi-escritor (el commit
            # de git ya firma quién tejió).
            if nota.meta:
                nota.meta["actualizada"] = date.today()
            nota.ruta.write_text(nota.texto_completo(), encoding="utf-8")
            aplicados += 1
            por_nota[s["nota"]] = por_nota.get(s["nota"], 0) + 1

    return aplicados
