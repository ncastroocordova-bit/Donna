"""Capa de evaluación (Plan v5 §5). Corre los casos de evals/casos.yaml contra el
brain y juzga cada respuesta con un Claude evaluador. Reporta pasa/falla.

Regla del proyecto: ningún cambio (constitución, modelo, módulo) se da por bueno
hasta que estos evals pasan. Cada módulo agrega sus casos a casos.yaml.

Uso:  python evals.py
"""
import asyncio
import sys
from pathlib import Path

import yaml
from anthropic import AsyncAnthropic

import brain
from config import settings

_judge = AsyncAnthropic(api_key=settings.anthropic_api_key)
CASOS = Path(__file__).parent / "evals" / "casos.yaml"

JUEZ_SYSTEM = (
    "Eres un evaluador estricto del agente 'Donna' (personalidad: Donna Paulsen de Suits: "
    "filosa, cálida, con humor, directa, nunca genérica ni robótica). Te doy una ENTRADA, un "
    "CRITERIO esperado y la RESPUESTA del agente. En la PRIMERA línea responde exactamente "
    "PASA o FALLA. En la segunda, una razón breve."
)


async def _juzgar(entrada: str, criterio: str, respuesta: str) -> tuple[bool, str]:
    r = await _judge.messages.create(
        model=settings.model_brain,
        max_tokens=150,
        system=JUEZ_SYSTEM,
        messages=[{"role": "user", "content": f"ENTRADA:\n{entrada}\n\nCRITERIO:\n{criterio}\n\nRESPUESTA:\n{respuesta}"}],
    )
    veredicto = r.content[0].text.strip()
    return veredicto.upper().startswith("PASA"), veredicto


async def correr() -> bool:
    casos = yaml.safe_load(CASOS.read_text(encoding="utf-8"))
    print(f"Corriendo {len(casos)} casos...\n")
    pasados = 0
    for i, c in enumerate(casos):
        if i > 0:
            # Voyage AI free tier: 3 RPM. 25s entre casos (cada caso hace 1-2 embeds).
            await asyncio.sleep(25)
        # off_record=True: los casos de eval no deben contaminar la memoria real.
        respuesta, _ = await brain.responder(c["entrada"], [], off_record=True)
        ok, veredicto = await _juzgar(c["entrada"], c["espera"], respuesta)
        pasados += ok
        print(f"[{'PASA' if ok else 'FALLA'}] {c['id']} ({c['tipo']})")
        if not ok:
            print("   " + veredicto.replace("\n", " | "))
    print(f"\n{pasados}/{len(casos)} casos PASA")
    return pasados == len(casos)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(correr()) else 1)
