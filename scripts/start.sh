#!/usr/bin/env bash
# Arranque en Railway: clona el repo de Córtex (código + vault, una sola unidad)
# si no está presente, luego arranca Donna. El contenedor es efímero — cada
# deploy/restart puede perder el filesystem, así que clonar en cada arranque
# es lo esperado, no un parche. arc_guardar hace pull antes y push después de
# cada escritura (CORTEX_GIT_AUTO=1), así que nada se pierde entre arranques.
set -euo pipefail

CORTEX_DIR="${CORTEX_LOCAL_PATH:-/app/_cortex}"

if [ -n "${CORTEX_GITHUB_TOKEN:-}" ] && [ ! -d "$CORTEX_DIR/.git" ]; then
  echo "[start.sh] Clonando Córtex en $CORTEX_DIR..."
  git clone --depth 1 "https://x-access-token:${CORTEX_GITHUB_TOKEN}@github.com/ncastroocordova-bit/cortex.git" "$CORTEX_DIR"
  git -C "$CORTEX_DIR" config user.email "donna@noomi-cookies.local"
  git -C "$CORTEX_DIR" config user.name "Donna"
else
  echo "[start.sh] Sin CORTEX_GITHUB_TOKEN o repo ya presente; arc_guardar degradará si falta."
fi

export CORTEX_VAULT="${CORTEX_VAULT:-$CORTEX_DIR/vault}"
export CORTEX_AUTOR="${CORTEX_AUTOR:-donna}"
export CORTEX_GIT_AUTO="${CORTEX_GIT_AUTO:-1}"

exec python main.py
