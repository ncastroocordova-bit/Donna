"""
Sincronización git del vault: el patrón multi-escritor.
Regla de oro: pull --rebase ANTES de escribir, commit + push DESPUÉS.
Si el vault no es un repo git, todas las funciones son inofensivas (no-op),
así el mismo código corre en desarrollo local sin git.
"""
from __future__ import annotations

import subprocess

from . import config


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=config.VAULT_PATH,
        capture_output=True,
        text=True,
        timeout=60,
    )


def es_repo() -> bool:
    try:
        return _git("rev-parse", "--is-inside-work-tree").returncode == 0
    except Exception:
        return False


def pull() -> str:
    if not es_repo():
        return "no-git"
    r = _git("pull", "--rebase", "--autostash")
    return "ok" if r.returncode == 0 else f"error-pull: {r.stderr.strip()[:200]}"


def commit_push(mensaje: str) -> str:
    if not es_repo():
        return "no-git"
    _git("add", "-A")
    # Chequeo independiente del locale de git (no busca "nothing to commit").
    hay_cambios = bool(_git("status", "--porcelain").stdout.strip())
    if hay_cambios:
        r = _git("commit", "-m", f"[cortex] {mensaje}")
        if r.returncode != 0:
            # Identidad sin configurar, hook que falla, etc.: no seguir al
            # push como si nada — el agente debe enterarse.
            detalle = (r.stderr or r.stdout).strip()[:200]
            return f"error-commit: {detalle}"

    # Push SIEMPRE, haya o no commit nuevo: un push anterior fallido (sin
    # red, remoto caído) deja commits locales varados que hay que empujar.
    push = _git("push")
    if push.returncode == 0:
        return "ok" if hay_cambios else "sin-cambios"

    # Otro agente empujó primero: reintenta una vez con rebase.
    _git("pull", "--rebase", "--autostash")
    push = _git("push")
    if push.returncode == 0:
        return "ok" if hay_cambios else "sin-cambios"
    return f"error-push: {push.stderr.strip()[:200]}"


def sincronizar(mensaje: str = "sync") -> str:
    """Pull + commit + push en una sola llamada."""
    estado_pull = pull()
    estado_push = commit_push(mensaje)
    return f"pull={estado_pull} push={estado_push}"
