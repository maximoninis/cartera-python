"""Paso 1 del guion: validar el motor con un puñado de movimientos de
prueba a mano, ANTES de tocar la UI. Correr con:

    python tests/test_motor.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modelo import Movimiento
from motor import recalcular, chequeo_identidad, pnl_realizado_total, pnl_no_realizado


def caso_basico():
    """Depósito, compra, otra compra, venta parcial (FIFO), dividendo.
    Todo en ARS para no meter tipo de cambio todavía."""
    movs = [
        Movimiento(id="1", fecha="2026-01-01", tipo="deposito", broker="cocos",
                   moneda="ARS", monto_neto=1_000_000),

        Movimiento(id="2", fecha="2026-01-05", tipo="compra", broker="cocos",
                   moneda="ARS", activo_id="SPY", cantidad=10, precio_unitario=50_000,
                   monto_bruto=500_000, comisiones=2_000, impuestos=500,
                   monto_neto=-502_500),

        Movimiento(id="3", fecha="2026-02-10", tipo="compra", broker="cocos",
                   moneda="ARS", activo_id="SPY", cantidad=5, precio_unitario=55_000,
                   monto_bruto=275_000, comisiones=1_100, impuestos=275,
                   monto_neto=-276_375),

        # vende 8 de las 15 (FIFO: consume las 10 primeras -> 8 del lote 1)
        Movimiento(id="4", fecha="2026-03-01", tipo="venta", broker="cocos",
                   moneda="ARS", activo_id="SPY", cantidad=-8, precio_unitario=58_000,
                   monto_bruto=464_000, comisiones=2_088, impuestos=522,
                   monto_neto=461_390),

        Movimiento(id="5", fecha="2026-03-15", tipo="dividendo", broker="cocos",
                   moneda="ARS", activo_id="SPY", monto_neto=3_200),
    ]

    for m in movs:
        errores = m.validar()
        assert not errores, f"movimiento {m.id} inválido: {errores}"

    estado = recalcular(movs)

    # precio de mercado hoy para lo que queda (15 - 8 = 7 SPY)
    precios = {"SPY": 60_000}

    chequeo = chequeo_identidad(estado, precios)
    print("cajas:", dict(estado.cajas))
    print("posición SPY: cantidad =", estado.posicion("cocos", "SPY").cantidad,
          "costo promedio =", round(estado.posicion("cocos", "SPY").costo_promedio, 2))
    print("pnl realizado:", round(pnl_realizado_total(estado), 2))
    print("pnl no realizado:", round(pnl_no_realizado(estado, precios), 2))
    print("chequeo identidad:", chequeo)

    assert chequeo["ok"], f"la identidad contable NO cierra: {chequeo}"
    assert estado.posicion("cocos", "SPY").cantidad == 7

    # snapshot histórico: cómo estaba la cartera antes de la venta
    estado_previo = recalcular(movs, hasta="2026-02-28")
    assert estado_previo.posicion("cocos", "SPY").cantidad == 15
    print("OK — snapshot al 2026-02-28: SPY =", estado_previo.posicion("cocos", "SPY").cantidad)


if __name__ == "__main__":
    caso_basico()
    print("\n✔ todos los casos pasaron — la identidad contable cierra")
