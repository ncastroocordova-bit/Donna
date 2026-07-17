"""
Configuración central de Córtex.
Todo se controla por variables de entorno para que el mismo código
funcione en tu PC, en Railway (Donna / Noomi Bot) y en el MCP.
"""
import os
from pathlib import Path

# Carga cortex/.env si existe (Task Scheduler y cron no heredan la sesión).
# setdefault: una variable ya presente en el entorno SIEMPRE gana al .env.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    for _linea in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _linea = _linea.strip()
        if _linea and not _linea.startswith("#") and "=" in _linea:
            _clave, _valor = _linea.split("=", 1)
            os.environ.setdefault(_clave.strip(), _valor.strip().strip('"').strip("'"))

# Ruta al vault. Por defecto: carpeta "vault" junto al paquete.
VAULT_PATH = Path(
    os.environ.get(
        "CORTEX_VAULT",
        Path(__file__).resolve().parent.parent / "vault",
    )
).resolve()

# Identidad del escritor (queda registrada en el frontmatter y en los commits).
# Valores esperados: nico | donna | noomi-bot | claude | claude-code
AUTOR = os.environ.get("CORTEX_AUTOR", "desconocido")

# Si es "1", cada escritura hace git pull antes y commit+push después.
GIT_AUTO = os.environ.get("CORTEX_GIT_AUTO", "0") == "1"

# Si es "1", el loop nocturno aplica los wikilinks sugeridos (modo conservador).
AUTOLINK = os.environ.get("CORTEX_AUTOLINK", "0") == "1"

# Días sin actualizar para considerar "obsoleta" una nota de tipo proyecto/estado.
DIAS_OBSOLETA = int(os.environ.get("CORTEX_DIAS_OBSOLETA", "30"))

# Días que una nota puede vivir en 00-Inbox antes de que el lint la reclame.
DIAS_INBOX = int(os.environ.get("CORTEX_DIAS_INBOX", "7"))

# Carpetas que el lint y la búsqueda ignoran.
CARPETAS_IGNORADAS = {".obsidian", ".trash", ".git", "90-Meta"}

# Esquema de frontmatter: campos obligatorios en toda nota.
CAMPOS_OBLIGATORIOS = ["titulo", "tipo", "area", "creada", "actualizada", "autor"]

TIPOS_VALIDOS = {
    "concepto", "proyecto", "persona", "decision",
    "recurso", "diario", "reunion", "meta",
}

AREAS_VALIDAS = {
    "holding", "personal", "noomi", "ncc", "universidad", "casa", "recursos", "meta",
}
