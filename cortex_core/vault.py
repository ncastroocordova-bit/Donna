"""
Operaciones base sobre el vault: leer, escribir, agregar, listar.
Toda nota es Markdown con frontmatter YAML y wikilinks [[...]].
Este módulo es la única puerta de escritura: Donna, Noomi Bot, el MCP
y los loops usan estas mismas funciones.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from . import config
from . import gitsync

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# ---------------------------------------------------------------- utilidades

def slugify(texto: str) -> str:
    """Convierte un título en nombre de archivo seguro, conservando legibilidad."""
    texto = texto.strip()
    # Quita caracteres prohibidos en nombres de archivo, mantiene tildes y ñ.
    texto = re.sub(r'[\\/:*?"<>|#^\[\]]', "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto[:120]


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar títulos y links."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.lower().strip()


def _como_fecha(valor) -> date | None:
    """Convierte date, datetime o string ISO ('2026-07-12', con o sin hora,
    con o sin comillas en el YAML) a date. None si no se puede interpretar."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            # datetime.fromisoformat acepta fecha sola Y fecha con hora
            # (Obsidian a veces escribe propiedades como 2026-07-12T09:30).
            return datetime.fromisoformat(valor.strip()).date()
        except ValueError:
            return None
    return None


def parse_frontmatter(texto: str) -> tuple[dict, str]:
    """Separa el frontmatter YAML del cuerpo. Devuelve ({}, texto) si no hay."""
    m = FRONTMATTER_RE.match(texto)
    if not m:
        return {}, texto
    try:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, texto[m.end():]


class _DumperPlano(yaml.SafeDumper):
    """SafeDumper sin anclas/alias YAML: si dos campos comparten el mismo
    objeto (p.ej. creada y actualizada con el mismo date), PyYAML emitiría
    `&id001`/`*id001`, que ensucia el frontmatter en Obsidian."""

    def ignore_aliases(self, data):
        return True


def build_frontmatter(meta: dict) -> str:
    cuerpo = yaml.dump(meta, Dumper=_DumperPlano, allow_unicode=True,
                       sort_keys=False, default_flow_style=None)
    return f"---\n{cuerpo}---\n"


# ------------------------------------------------------------------- modelo

@dataclass
class Nota:
    ruta: Path
    meta: dict = field(default_factory=dict)
    cuerpo: str = ""

    @property
    def titulo(self) -> str:
        return str(self.meta.get("titulo") or self.ruta.stem)

    @property
    def ruta_relativa(self) -> str:
        return str(self.ruta.relative_to(config.VAULT_PATH))

    @property
    def wikilinks(self) -> list[str]:
        return [l.strip() for l in WIKILINK_RE.findall(self.cuerpo)]

    def texto_completo(self) -> str:
        fm = build_frontmatter(self.meta) if self.meta else ""
        return fm + self.cuerpo


# ---------------------------------------------------------------- lectura

def listar_notas(carpeta: str | None = None) -> list[Path]:
    """Todas las rutas .md del vault, ignorando carpetas de sistema."""
    base = config.VAULT_PATH / carpeta if carpeta else config.VAULT_PATH
    rutas = []
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(config.VAULT_PATH)
        if any(parte in config.CARPETAS_IGNORADAS for parte in rel.parts[:-1]):
            continue
        rutas.append(p)
    return rutas


def cargar(ruta: Path) -> Nota:
    texto = ruta.read_text(encoding="utf-8")
    meta, cuerpo = parse_frontmatter(texto)
    return Nota(ruta=ruta, meta=meta, cuerpo=cuerpo)


def resolver_todos(identificador: str) -> list[Path]:
    """Todas las notas que coinciden con el identificador.
    Una ruta relativa exacta gana siempre; si no, coincidencias por nombre
    de archivo y, en su defecto, por título del frontmatter. Más de un
    resultado significa que el identificador es ambiguo."""
    directo = config.VAULT_PATH / identificador
    if directo.suffix != ".md":
        directo = directo.with_suffix(".md")
    if directo.exists():
        return [directo]

    objetivo = _normalizar(Path(identificador).stem)
    por_nombre: list[Path] = []
    por_titulo: list[Path] = []
    for p in listar_notas():
        if _normalizar(p.stem) == objetivo:
            por_nombre.append(p)
        elif _normalizar(cargar(p).titulo) == objetivo:
            por_titulo.append(p)
    return por_nombre if por_nombre else por_titulo


def resolver(identificador: str) -> Path | None:
    """Encuentra una nota por ruta relativa, nombre de archivo o título.
    Si hay varias coincidencias devuelve la primera; para detectar
    ambigüedad usa resolver_todos."""
    coincidencias = resolver_todos(identificador)
    return coincidencias[0] if coincidencias else None


def leer_nota(identificador: str) -> Nota | None:
    ruta = resolver(identificador)
    return cargar(ruta) if ruta else None


def actividad_reciente(dias: int = 7, limite: int = 30) -> list[dict]:
    """Notas modificadas en los últimos N días, según frontmatter o mtime."""
    resultados = []
    hoy = date.today()
    for p in listar_notas():
        nota = cargar(p)
        act = _como_fecha(nota.meta.get("actualizada"))
        if act is None:
            act = date.fromtimestamp(p.stat().st_mtime)
        delta = (hoy - act).days
        if delta <= dias:
            resultados.append({
                "ruta": nota.ruta_relativa,
                "titulo": nota.titulo,
                "actualizada": str(act),
                "autor": nota.meta.get("autor", "?"),
                "hace_dias": delta,
            })
    resultados.sort(key=lambda r: r["hace_dias"])
    return resultados[:limite]


# --------------------------------------------------------------- escritura

def escribir_nota(
    titulo: str,
    contenido: str,
    carpeta: str = "00-Inbox",
    tipo: str = "concepto",
    area: str = "personal",
    tags: list[str] | None = None,
    autor: str | None = None,
    sincronizar: bool | None = None,
) -> Nota:
    """
    Crea una nota nueva o reemplaza el cuerpo de una existente,
    preservando su fecha de creación. Frontmatter siempre completo.
    """
    autor = autor or config.AUTOR
    sincronizar = config.GIT_AUTO if sincronizar is None else sincronizar
    if sincronizar:
        gitsync.pull()

    carpeta_path = config.VAULT_PATH / carpeta
    carpeta_path.mkdir(parents=True, exist_ok=True)
    ruta = carpeta_path / f"{slugify(titulo)}.md"

    # Objeto date, NO str: PyYAML serializa date sin comillas y el round-trip
    # devuelve date, que es lo que linter y actividad_reciente esperan.
    hoy = date.today()
    if ruta.exists():
        existente = cargar(ruta)
        meta = existente.meta
        meta["actualizada"] = hoy
        meta["autor"] = autor
        if tags:
            meta["tags"] = sorted(set(meta.get("tags") or []) | set(tags))
    else:
        meta = {
            "titulo": titulo,
            "tipo": tipo,
            "area": area,
            "tags": tags or [],
            "creada": hoy,
            "actualizada": hoy,
            "autor": autor,
            "estado": "activa",
        }

    nota = Nota(ruta=ruta, meta=meta, cuerpo=contenido.rstrip() + "\n")
    ruta.write_text(nota.texto_completo(), encoding="utf-8")

    if sincronizar:
        gitsync.commit_push(f"nota: {titulo} ({autor})")
    return nota


def agregar_a_nota(
    identificador: str,
    contenido: str,
    autor: str | None = None,
    sincronizar: bool | None = None,
) -> Nota:
    """Agrega contenido al final de una nota existente y actualiza el frontmatter."""
    autor = autor or config.AUTOR
    sincronizar = config.GIT_AUTO if sincronizar is None else sincronizar
    if sincronizar:
        gitsync.pull()

    coincidencias = resolver_todos(identificador)
    if not coincidencias:
        raise FileNotFoundError(f"No existe la nota: {identificador}")
    if len(coincidencias) > 1:
        opciones = ", ".join(
            str(p.relative_to(config.VAULT_PATH)) for p in coincidencias
        )
        raise ValueError(
            f"'{identificador}' es ambiguo ({len(coincidencias)} notas: "
            f"{opciones}). Usa la ruta relativa."
        )
    ruta = coincidencias[0]

    nota = cargar(ruta)
    nota.meta["actualizada"] = date.today()
    nota.meta["autor"] = autor
    nota.cuerpo = nota.cuerpo.rstrip() + "\n\n" + contenido.rstrip() + "\n"
    ruta.write_text(nota.texto_completo(), encoding="utf-8")

    if sincronizar:
        gitsync.commit_push(f"append: {nota.titulo} ({autor})")
    return nota
