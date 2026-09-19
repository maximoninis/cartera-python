"""Importador de Cocos Capital.

`detectar(filas)` mira las columnas. `interpretar(filas)` devuelve una
lista de MovimientoCandidato: cada uno trae el Movimiento armado (o None
si no se pudo armar con confianza) + un estado:

    'ok'       -> mapeo seguro, se puede meter a la base tal cual
    'revisar'  -> mapeo tentativo, necesita que el usuario lo confirme
                  antes de darlo por bueno (ver notas abajo)
    'rechazado'-> no se pudo interpretar la fila, se descarta con motivo

Reglas de negocio de Cocos CONFIRMADAS por el usuario (13/09/2026):
  - 'Compra' / 'Compra Dolar Mep'                     -> compra
  - 'Venta' / 'Venta Dolar Mep'                        -> venta
  - 'Recibo De Cobro'            -> deposito (ARS)
  - 'Recibo De Cobro Dolares'    -> deposito (USD)
  - 'Orden De Pago' / 'Orden De Pago Usd'              -> retiro
  - 'Liquidacion Suscripcion Fci' / 'Liq Suscripcion Fci Usd' /
    'Liquidacion Suscripcion Fci Hb'                   -> compra de FCI
  - 'Liquidacion Rescate Fci' / 'Liq Rescate Fci Usd' /
    'Liquidacion Rescate Fci Hb'                       -> venta de FCI
  - 'DIVIDENDOS EN ESPECIE' / 'Dividendos'             -> dividendo
  - 'RENTA Y AMORTIZACION EN ESPECIE' / 'Renta y Amortizacion USD' /
    'Renta Y Amortizacion'                             -> interes (renta)

Nota sobre 'Compra Dolar Mep'/'Venta Dolar Mep': a diferencia del caso
de Galicia con el bono AL30 (donde compra en ARS + venta en USD con el
MISMO número de operación eran las dos patas de una sola conversión),
acá cada fila de Cocos ya viene con su 'total' completo y balanceado
en una sola moneda — es simplemente una compra/venta normal pagada con
dólares que ya estaban convertidos por otro lado. No se emparejan.

Ignorados a pedido del usuario (no valen la pena / no corresponde
registrarlos como movimiento):
  - 'Nota De Credito Conversion' / 'Nota De Credito Conversion Cable'
       -> vueltos/redondeo de conversiones, montos de centavos.
  - 'Venta Registracion USD' + 'Compra Registracion ARS' -> compra y
       venta de un bono (ON) que el usuario ya no tiene; no vale la
       pena reconstruir esa posición cerrada.
  - 'Concepto EXT migracion' -> artefacto administrativo de migración
       de cuenta, moneda 'EXT' (no es ARS ni USD), montos de centavos.
"""
import csv
import re
from datetime import datetime

from modelo import Movimiento

COLUMNAS_ESPERADAS = {
    "nroTicket", "nroComprobante", "fechaEjecucion", "fechaLiquidacion",
    "tipoOperacion", "instrumento", "moneda", "mercado", "cantidad",
    "precio", "montoBruto", "comision", "ddmm", "iva", "otros", "total",
}

TIPOS_COMPRA = {"Compra", "Compra Dolar Mep",
                 "Liquidacion Suscripcion Fci", "Liq Suscripcion Fci Usd", "Liquidacion Suscripcion Fci Hb"}
TIPOS_VENTA = {"Venta", "Venta Dolar Mep",
               "Liquidacion Rescate Fci", "Liq Rescate Fci Usd", "Liquidacion Rescate Fci Hb"}
TIPOS_DEPOSITO = {"Recibo De Cobro", "Recibo De Cobro Dolares"}
TIPOS_RETIRO = {"Orden De Pago", "Orden De Pago Usd"}

# tipoOperacion -> tipo de Movimiento, para los ingresos "en especie"/renta
MAPEO_RENTA = {
    "DIVIDENDOS EN ESPECIE": "dividendo",
    "Dividendos": "dividendo",
    "RENTA Y AMORTIZACION EN ESPECIE": "interes",
    "Renta y Amortizacion USD": "interes",
    "Renta Y Amortizacion": "interes",
}

TIPOS_IGNORADOS = {
    "Nota De Credito Conversion",
    "Nota De Credito Conversion Cable",
    "Venta Registracion USD",
    "Compra Registracion ARS",
    "Concepto EXT migracion",
}


def _num(s: str) -> float:
    """'1.246,183' -> 1246.183 ; '-4,784' -> -4.784 ; '' -> 0.0"""
    s = (s or "").strip()
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    return float(s)


def _fecha(s: str) -> str:
    """'05-01-2026' -> '2026-01-05'"""
    return datetime.strptime(s.strip(), "%d-%m-%Y").strftime("%Y-%m-%d")


def _activo_id(instrumento: str) -> str | None:
    """Extrae el ticker entre paréntesis, ej. '...SPDR S&P 500 (SPY)' -> 'SPY'."""
    if not instrumento:
        return None
    m = re.search(r"\(([A-Z0-9]+)\)\s*$", instrumento.strip())
    return m.group(1) if m else instrumento.strip() or None


def detectar(filas: list[dict]) -> bool:
    if not filas:
        return False
    return COLUMNAS_ESPERADAS.issubset(set(filas[0].keys()))


def leer_csv(ruta: str) -> list[dict]:
    with open(ruta, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def interpretar(filas: list[dict]) -> list[dict]:
    candidatos = []

    for i, fila in enumerate(filas):
        tipo_op = fila["tipoOperacion"].strip()
        huella = fila["nroComprobante"].strip() or fila["nroTicket"].strip()
        fecha = _fecha(fila["fechaEjecucion"])
        fecha_liq = _fecha(fila["fechaLiquidacion"]) if fila["fechaLiquidacion"].strip() else fecha
        moneda = fila["moneda"].strip()
        total = _num(fila["total"])
        cantidad = _num(fila["cantidad"])
        precio = _num(fila["precio"])
        monto_bruto = _num(fila["montoBruto"])
        comision = _num(fila["comision"])
        ddmm = _num(fila["ddmm"])
        iva = _num(fila["iva"])
        otros = _num(fila["otros"])
        activo_id = _activo_id(fila["instrumento"])
        costos = abs(comision) + abs(ddmm) + abs(iva) + abs(otros)

        base = dict(
            id=f"cocos-{huella}",
            fecha=fecha,
            fecha_liquidacion=fecha_liq,
            broker="cocos",
            moneda=moneda,
            huella=huella,
            fuente="cocos",
            nota=tipo_op,
        )

        mov = None
        estado = "revisar"
        motivo = ""

        if tipo_op in TIPOS_COMPRA:
            mov = Movimiento(
                **base, tipo="compra", activo_id=activo_id,
                cantidad=cantidad, precio_unitario=precio,
                monto_bruto=abs(monto_bruto), comisiones=costos,
                monto_neto=total,
            )
            estado = "ok"

        elif tipo_op in TIPOS_VENTA:
            mov = Movimiento(
                **base, tipo="venta", activo_id=activo_id,
                cantidad=cantidad, precio_unitario=precio,
                monto_bruto=abs(monto_bruto), comisiones=costos,
                monto_neto=total,
            )
            estado = "ok"

        elif tipo_op in TIPOS_DEPOSITO:
            mov = Movimiento(**base, tipo="deposito", monto_neto=total)
            estado = "ok"

        elif tipo_op in TIPOS_RETIRO:
            mov = Movimiento(**base, tipo="retiro", monto_neto=total)
            estado = "ok"

        elif tipo_op in MAPEO_RENTA:
            mov = Movimiento(
                **base, tipo=MAPEO_RENTA[tipo_op], activo_id=activo_id,
                monto_neto=total,
            )
            estado = "ok"

        elif tipo_op in TIPOS_IGNORADOS:
            estado = "ignorado"
            motivo = f"tipoOperacion '{tipo_op}' — ignorado a pedido del usuario"

        else:
            estado = "rechazado"
            motivo = f"tipoOperacion desconocido: '{tipo_op}'"

        if mov is not None:
            errores = mov.validar()
            if errores and estado == "ok":
                estado = "rechazado"
                motivo = "; ".join(errores)

        candidatos.append({
            "fila": i + 2,  # +2: header + índice 1-based
            "tipo_operacion_original": tipo_op,
            "estado": estado,
            "motivo": motivo,
            "movimiento": mov.to_dict() if mov else None,
        })

    return candidatos
