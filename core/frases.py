"""Variedad de los textos FIJOS de Donna (brief/cierre) — que no se vean predeterminados.

Versión lean: pools de variantes en la voz de Donna, elección aleatoria evitando la última
usada (estado en memoria del proceso — se reinicia con cada deploy, sin DB). Los `callback_data`
de los botones NO cambian: solo varía el TEXTO de la pregunta, así el ruteo de on_callback intacto.

Las aperturas del brief/cierre las genera el LLM (varían solas); acá van solo los strings fijos
que hoy salen idénticos todos los días. Si más adelante se quiere no-repetición estricta entre
días, se agrega la tabla textos_emitidos (migración 013) y esta elección lee de ahí.
"""
import random

# key → variantes (redactadas en la voz de Donna; el eje sueño puede dejar caer su tono).
POOLS = {
    "sueno_dormi": [
        "¿A qué hora te dormiste anoche?",
        "Primero lo primero: ¿a qué hora caíste anoche?",
        "¿Y anoche, a qué hora te dormiste?",
        "Cuéntame la hora en que te dormiste anoche.",
    ],
    # MITs y evento: texto o voz, como quiera Nico. La cadena del cierre (main._procesar_entrada)
    # los captura igual por los dos canales, así que las frases no empujan un formato.
    "mits": [
        "Dime tus 1 a 3 prioridades de mañana — escríbelas o mándame un audio. 🎙️",
        "¿Qué sí o sí tiene que pasar mañana? Escríbelo o grábamelo. 🎙️",
        "Tus 1–3 imprescindibles de mañana: por texto o por voz, como prefieras. 🎙️",
        "¿Qué mueve la aguja mañana? Dímelo escrito o en un audio. 🎙️",
    ],
    "evento_contextual": [
        "¿Hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?",
        "¿Pasó algo hoy que no dependía de ti y te desarmó el día?",
        "Fuera de lo tuyo: ¿algo hoy que se cruzó y no controlabas?",
        "¿Algo externo hoy que te haya movido el ánimo o los planes?",
    ],
    # Primera comida: se sacó del panel del cierre (22:00) porque a esa hora ya se le había
    # olvidado — se pregunta a mediodía, cuando ya pasó y todavía se acuerda (Fase 3).
    "primera_comida_mediodia": [
        "¿A qué hora comiste hoy por primera vez?",
        "Tu primera comida de hoy, ¿a qué hora fue?",
        "¿Cuándo rompiste el ayuno hoy?",
        "Dime la hora de tu primera comida de hoy.",
    ],
    # Peso: pasó de cada noche a UNA vez por semana (domingo) — se mueve lento, preguntarlo a
    # diario era mucha fricción para poca señal nueva.
    "peso_semanal": [
        "Cierre de semana: ¿cuánto marcaste en la pesa?",
        "Y lo de una vez por semana: tu peso, ¿cuánto fue?",
        "Antes de cerrar la semana, pásame tu peso.",
        "El peso de la semana, ¿en cuánto quedaste?",
    ],
}

_ultima: dict[str, str] = {}  # key → última variante usada (memoria del proceso)


def frase(key: str) -> str:
    """Elige una variante del pool evitando la última usada para ese key. '' si el key no existe."""
    pool = POOLS.get(key)
    if not pool:
        return ""
    opciones = [f for f in pool if f != _ultima.get(key)] or pool
    elegida = random.choice(opciones)
    _ultima[key] = elegida
    return elegida
