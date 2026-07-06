"""Ordena una vez la hoja `Transacciones` por Fecha (arregla el desorden histórico).

De aquí en adelante `confirmar_digest` la reordena sola tras cada "Aceptar todo"; esto es
solo para el desorden acumulado. Corre: `python -m scripts.ordenar_transacciones`.
"""
import asyncio

from core import sheets


async def _main() -> None:
    ok = await sheets.ordenar_por_columna("Transacciones", "Fecha", sheet_id=sheets.fin_id())
    print("Transacciones ordenada por Fecha." if ok else "No había nada que ordenar (o no pude resolver la hoja).")


if __name__ == "__main__":
    asyncio.run(_main())
