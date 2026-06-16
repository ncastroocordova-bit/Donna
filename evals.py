"""Capa de evaluación (Plan v5 §5). Corre los casos de evals/casos.yaml contra el
brain y juzga cada respuesta. Reporta pasa/falla.

Regla del proyecto: ningún cambio (constitución, modelo, módulo) se da por bueno
hasta que estos evals pasan. Cada módulo agrega sus casos a casos.yaml.

Uso:
  python evals.py              # corre el modelo de config.py (producción)
  python evals.py --comparar   # corre Sonnet 4.6 vs Opus 4.8 lado a lado (potencia + costo)
"""
import asyncio
import sys
from pathlib import Path

import anthropic
import yaml
from anthropic import AsyncAnthropic

import brain
from config import settings

_judge = AsyncAnthropic(api_key=settings.anthropic_api_key)
CASOS = Path(__file__).parent / "evals" / "casos.yaml"

# El juez es fijo: así la comparación entre modelos de Donna es justa y no queda
# contaminada por la variabilidad (ni los 500 transitorios) del modelo evaluado.
JUDGE_MODEL = "claude-sonnet-4-6"

# Tarifas USD por millón de tokens (cache write = 5min). Fuente: pricing oficial.
PRICING = {
    "claude-opus-4-8":   {"in": 5.0, "out": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cache_write": 3.75, "cache_read": 0.30},
}

JUEZ_SYSTEM = (
    "Eres un evaluador estricto del agente 'Donna' (personalidad: Donna Paulsen de Suits: "
    "filosa, cálida, con humor, directa, nunca genérica ni robótica). Te doy una ENTRADA, un "
    "CRITERIO esperado y la RESPUESTA del agente. En la PRIMERA línea responde exactamente "
    "PASA o FALLA. En la segunda, una razón breve."
)

# Errores transitorios del servidor que justifican reintento con backoff.
_RETRYABLE = (
    anthropic.InternalServerError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.OverloadedError,
)


async def _reintentar(factory, intentos: int = 5):
    """Ejecuta una corrutina con backoff exponencial ante 500/timeout/overload.
    `factory` es un callable sin args que devuelve una corrutina nueva en cada intento."""
    for n in range(intentos):
        try:
            return await factory()
        except _RETRYABLE:
            if n == intentos - 1:
                raise
            await asyncio.sleep(2 ** n)


async def _juzgar(entrada: str, criterio: str, respuesta: str) -> tuple[bool, str]:
    r = await _judge.messages.create(
        model=JUDGE_MODEL,
        max_tokens=150,
        system=JUEZ_SYSTEM,
        messages=[{"role": "user", "content": f"ENTRADA:\n{entrada}\n\nCRITERIO:\n{criterio}\n\nRESPUESTA:\n{respuesta}"}],
    )
    veredicto = r.content[0].text.strip()
    return veredicto.upper().startswith("PASA"), veredicto


def _tools_esperadas(c: dict) -> list[str]:
    """Devuelve la lista de tools que el caso exige (string único o lista)."""
    if c.get("tools_esperadas"):
        return list(c["tools_esperadas"])
    if c.get("tool_esperada"):
        return [c["tool_esperada"]]
    return []


def _costo(uso: dict, model: str) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (
        uso["input_tokens"] / 1e6 * p["in"]
        + uso["output_tokens"] / 1e6 * p["out"]
        + uso["cache_creation_input_tokens"] / 1e6 * p["cache_write"]
        + uso["cache_read_input_tokens"] / 1e6 * p["cache_read"]
    )


async def correr(model: str, verbose: bool = True) -> dict:
    """Corre todos los casos con el brain en `model` (juez siempre JUDGE_MODEL).
    Devuelve {model, pasados, total, fallidos, uso}."""
    casos = yaml.safe_load(CASOS.read_text(encoding="utf-8"))
    if verbose:
        print(f"\n=== {model} — {len(casos)} casos ===\n")
    pasados = 0
    fallidos: list[str] = []
    uso_total = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    for i, c in enumerate(casos):
        if i > 0:
            await asyncio.sleep(5)  # breve pausa para no saturar la API

        # off_record + dry_run: los evals no escriben memoria NI ejecutan tools de
        # escritura → cero contaminación de la base de producción.
        respuesta, _, tools_llamadas, uso = await _reintentar(
            lambda: brain.responder(c["entrada"], [], off_record=True, model=model, dry_run=True, _return_tools=True)
        )
        for k in uso_total:
            uso_total[k] += uso[k]

        esperadas = _tools_esperadas(c)
        if esperadas:
            # Verificación directa: ¿se llamaron todas las herramientas correctas?
            faltan = [t for t in esperadas if t not in tools_llamadas]
            ok = not faltan
            veredicto = (
                f"PASA\nLlamo: {tools_llamadas}"
                if ok
                else f"FALLA\nFaltaron {faltan}. Herramientas usadas: {tools_llamadas or '(ninguna)'}"
            )
        else:
            ok, veredicto = await _reintentar(lambda: _juzgar(c["entrada"], c["espera"], respuesta))

        pasados += ok
        if not ok:
            fallidos.append(c["id"])
        if verbose:
            print(f"[{'PASA' if ok else 'FALLA'}] {c['id']} ({c['tipo']})")
            if not ok:
                print("   " + veredicto.replace("\n", " | "))

    if verbose:
        print(f"\n{pasados}/{len(casos)} casos PASA")
    return {"model": model, "pasados": pasados, "total": len(casos), "fallidos": fallidos, "uso": uso_total}


def _imprimir_comparacion(res_a: dict, res_b: dict) -> None:
    print("\n" + "=" * 60)
    print("COMPARACIÓN  Sonnet 4.6  vs  Opus 4.8")
    print("=" * 60)
    filas = [
        ("Casos PASA", lambda r: f"{r['pasados']}/{r['total']}"),
        ("Tokens entrada", lambda r: f"{r['uso']['input_tokens']:,}"),
        ("Tokens salida", lambda r: f"{r['uso']['output_tokens']:,}"),
        ("Cache write", lambda r: f"{r['uso']['cache_creation_input_tokens']:,}"),
        ("Cache read", lambda r: f"{r['uso']['cache_read_input_tokens']:,}"),
        ("Costo corrida (USD)", lambda r: f"${_costo(r['uso'], r['model']):.4f}"),
        ("Costo / 1.000 msgs (USD)", lambda r: f"${_costo(r['uso'], r['model']) / r['total'] * 1000:.2f}"),
    ]
    print(f"\n{'Métrica':<28}{'Sonnet 4.6':>16}{'Opus 4.8':>16}")
    print("-" * 60)
    for etiqueta, fn in filas:
        print(f"{etiqueta:<28}{fn(res_a):>16}{fn(res_b):>16}")
    for r, nombre in ((res_a, "Sonnet"), (res_b, "Opus")):
        if r["fallidos"]:
            print(f"\n{nombre} falló: {', '.join(r['fallidos'])}")
    print()


async def _main() -> bool:
    if "--comparar" in sys.argv:
        res_sonnet = await correr("claude-sonnet-4-6")
        res_opus = await correr("claude-opus-4-8")
        _imprimir_comparacion(res_sonnet, res_opus)
        return res_sonnet["pasados"] == res_sonnet["total"]
    res = await correr(settings.model_brain)
    return res["pasados"] == res["total"]


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(_main()) else 1)
