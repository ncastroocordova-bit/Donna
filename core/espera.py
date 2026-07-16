"""Espera — el mecanismo de 'Donna quedó esperando una respuesta específica' (Tanda 1 de la
auditoría de finanzas/Telegram). Antes cada corrección (categoría de una línea del digest, de un
ítem, desglose de un cargo, corrección de una inferencia) vivía como una llave suelta en
`user_data` que se tragaba el PRÓXIMO mensaje fuera cual fuera su contenido — sin poder cancelar,
sin validar que la respuesta tuviera sentido, y sin vencer nunca. Un mensaje sin relación (una
pregunta, un despiste) quedaba mal interpretado como la respuesta, y en más de un caso ese error
se aprendía después como regla permanente (comercio→categoría).

Esto unifica esas esperas en una sola pieza de estado por chat (`user_data['espera']`), con tres
reglas parejas para todas: se puede cancelar, expira sola, y quien la resuelve valida que la
respuesta tenga forma de tal antes de darla por buena — si no calza, se suelta y el mensaje sigue
su curso normal hacia el cerebro (ver `main._procesar_entrada`).

El gasto sin monto legible (`finanzas._gasto_incompleto`) es la excepción de forma: vive en un
global de finanzas, no acá, porque el tool que lo crea se llama desde el loop de tools del
cerebro sin contexto de Telegram. Pero sigue las mismas tres reglas, aplicadas localmente en ese
módulo (ver `finanzas.parece_monto` / `finanzas.hay_gasto_incompleto`)."""
import time
import unicodedata

TTL_SEGUNDOS = 15 * 60  # pasado esto, la espera muere sola: no insiste con algo que ya se enfrió.

_CANCELAR_KW = {
    "cancelar", "olvidalo", "dejalo", "dejalo asi", "nada", "no importa", "da lo mismo",
    "mejor no", "ya no", "olvidalo nomas",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def es_cancelacion(texto: str) -> bool:
    """¿Nico quiere abandonar la espera en curso? ('cancelar', 'olvídalo', 'déjalo así'...).
    Ojo: 'descartar'/'no es mío' NO son cancelación — son una respuesta válida dentro del propio
    flujo de corrección del digest (botar la línea), así que no van en esta lista."""
    return _norm(texto) in _CANCELAR_KW


def parece_respuesta_corta(texto: str, max_palabras: int = 6) -> bool:
    """¿Esta respuesta tiene forma de respuesta corta y directa (una categoría, un nombre,
    'descartar') y no de un mensaje suelto que llegó de casualidad mientras Donna esperaba algo?
    Rechaza vacío, preguntas, y frases largas — no valida el CONTENIDO, solo que tenga pinta de
    respuesta y no de otra cosa."""
    t = (texto or "").strip()
    if not t or "?" in t:
        return False
    return len(t.split()) <= max_palabras


def iniciar(user_data: dict, tipo: str, payload: dict | None = None) -> None:
    """Arranca (o reemplaza) la espera vigente de este chat."""
    user_data["espera"] = {"tipo": tipo, "payload": payload or {}, "creado": time.time()}


def activa(user_data: dict) -> dict | None:
    """La espera vigente, o None si no hay ninguna o si ya expiró (y en ese caso la limpia sola)."""
    esp = user_data.get("espera")
    if esp is None:
        return None
    if time.time() - esp.get("creado", 0) > TTL_SEGUNDOS:
        user_data.pop("espera", None)
        return None
    return esp


def limpiar(user_data: dict) -> None:
    user_data.pop("espera", None)
