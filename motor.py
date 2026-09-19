"""El motor: recorre movimientos ordenados por fecha y reconstruye el
estado de la cartera. Función pura, sin IO ni estado global.

    estado = recalcular(movimientos, hasta='2026-03-15')

Los movimientos son la única fuente de verdad — nunca se guarda una
"tenencia actual" aparte.
"""
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Lote:
    cantidad: float
    costo_unitario: float   # SOLO precio, sin comisiones/impuestos (ver §identidad)
    fecha: str
    moneda: str = "ARS"     # moneda del costo_unitario (heredada del movimiento que abrió el lote)
    costo_unitario_ars: float = 0.0   # costo convertido a ARS al tipo de cambio de SU fecha


@dataclass
class Posicion:
    lotes: list = field(default_factory=list)
    pnl_realizado: float = 0.0
    pnl_realizado_ars: float = 0.0

    @property
    def cantidad(self) -> float:
        return sum(l.cantidad for l in self.lotes)

    @property
    def costo_total(self) -> float:
        return sum(l.cantidad * l.costo_unitario for l in self.lotes)

    @property
    def costo_promedio(self) -> float:
        c = self.cantidad
        return self.costo_total / c if c else 0.0


@dataclass
class Estado:
    cajas: dict = field(default_factory=lambda: defaultdict(float))   # (broker,moneda) -> saldo
    posiciones: dict = field(default_factory=dict)                    # (broker,activo_id) -> Posicion
    capital_aportado: float = 0.0
    capital_aportado_ars: float = 0.0
    valor_apertura: float = 0.0     # posiciones declaradas por 'apertura' (no son un aporte)
    valor_apertura_ars: float = 0.0
    renta_cobrada: float = 0.0
    renta_cobrada_ars: float = 0.0
    comisiones: float = 0.0
    comisiones_ars: float = 0.0
    impuestos: float = 0.0
    impuestos_ars: float = 0.0
    transferencias_neto: float = 0.0
    transferencias_neto_ars: float = 0.0
    movimientos_aplicados: int = 0

    def posicion(self, broker: str, activo_id: str) -> Posicion:
        clave = (broker, activo_id)
        if clave not in self.posiciones:
            self.posiciones[clave] = Posicion()
        return self.posiciones[clave]


def buscar_tc(fecha: str, serie_tc: dict) -> float:
    """Tipo de cambio ARS/USD para 'fecha': exacto si existe, si no el
    más cercano hacia atrás (§3.3 del guion); si no hay ninguno anterior,
    el más antiguo disponible (mejor esfuerzo, no hay otra opción)."""
    if not serie_tc:
        raise ValueError("no hay serie de tipo de cambio cargada")
    if fecha in serie_tc:
        return serie_tc[fecha]
    anteriores = [f for f in serie_tc if f <= fecha]
    if anteriores:
        return serie_tc[max(anteriores)]
    return serie_tc[min(serie_tc)]  # mejor esfuerzo: no hay ninguna fecha anterior


def convertir_a_ars(monto: float, moneda: str, fecha: str, serie_tc: dict) -> float:
    if moneda == "ARS":
        return monto
    if moneda == "USD":
        return monto * buscar_tc(fecha, serie_tc)
    raise ValueError(f"moneda sin soporte de conversión: '{moneda}'")


def recalcular(movimientos, hasta: str | None = None, serie_tc: dict | None = None) -> Estado:
    """Reproduce todos los movimientos (o hasta cierta fecha inclusive) y
    devuelve el Estado resultante. No sabe nada de precios de mercado —
    eso se aplica después, sobre el Estado, en las funciones de abajo.

    Si se pasa `serie_tc` (tipo de cambio ARS/USD por fecha), además
    acumula en paralelo los mismos totales convertidos a ARS, cada
    movimiento al tipo de cambio de SU PROPIA fecha (§3.3 del guion) —
    lo necesario para que el chequeo de identidad cierre con una
    cartera que mezcla ARS y USD."""

    movs = [m for m in movimientos if hasta is None or m.fecha <= hasta]
    movs.sort(key=lambda m: (m.fecha, m.id))

    estado = Estado()
    conv = (lambda monto, moneda, fecha: convertir_a_ars(monto, moneda, fecha, serie_tc)) if serie_tc else None

    for m in movs:
        estado.cajas[(m.broker, m.moneda)] += m.monto_neto
        estado.comisiones += m.comisiones
        estado.impuestos += m.impuestos
        estado.movimientos_aplicados += 1
        if conv:
            estado.comisiones_ars += conv(m.comisiones, m.moneda, m.fecha)
            estado.impuestos_ars += conv(m.impuestos, m.moneda, m.fecha)

        if m.tipo in ("deposito", "retiro"):
            estado.capital_aportado += m.monto_neto
            if conv:
                estado.capital_aportado_ars += conv(m.monto_neto, m.moneda, m.fecha)

        elif m.tipo in ("compra", "apertura"):
            pos = estado.posicion(m.broker, m.activo_id)
            costo_unitario = (m.monto_bruto / m.cantidad) if m.cantidad else 0.0
            costo_unitario_ars = conv(costo_unitario, m.moneda, m.fecha) if conv else 0.0
            pos.lotes.append(Lote(m.cantidad, costo_unitario, m.fecha, m.moneda, costo_unitario_ars))
            if m.tipo == "apertura":
                estado.valor_apertura += m.monto_bruto
                if conv:
                    estado.valor_apertura_ars += conv(m.monto_bruto, m.moneda, m.fecha)

        elif m.tipo == "venta":
            pos = estado.posicion(m.broker, m.activo_id)
            a_vender = -m.cantidad
            costo_vendido = 0.0
            costo_vendido_ars = 0.0
            while a_vender > 1e-9 and pos.lotes:
                lote = pos.lotes[0]
                usado = min(lote.cantidad, a_vender)
                costo_vendido += usado * lote.costo_unitario
                costo_vendido_ars += usado * lote.costo_unitario_ars
                lote.cantidad -= usado
                a_vender -= usado
                if lote.cantidad <= 1e-9:
                    pos.lotes.pop(0)
            ingreso_bruto = m.monto_bruto
            pos.pnl_realizado += ingreso_bruto - costo_vendido
            if conv:
                pos.pnl_realizado_ars += conv(ingreso_bruto, m.moneda, m.fecha) - costo_vendido_ars

        elif m.tipo in ("dividendo", "interes"):
            estado.renta_cobrada += m.monto_neto
            if conv:
                estado.renta_cobrada_ars += conv(m.monto_neto, m.moneda, m.fecha)

        elif m.tipo == "conversion":
            estado.cajas[(m.broker, m.moneda_destino)] += m.cantidad_destino

        elif m.tipo == "transferencia":
            estado.transferencias_neto += m.monto_neto
            if conv:
                estado.transferencias_neto_ars += conv(m.monto_neto, m.moneda, m.fecha)

        # 'impuesto' / 'comision' sueltos: ya impactaron via monto_neto y
        # via estado.comisiones/estado.impuestos arriba, no hacen nada más.

    return estado


def pnl_realizado_total(estado: Estado) -> float:
    return sum(p.pnl_realizado for p in estado.posiciones.values())


def valor_posiciones(estado: Estado, precios: dict) -> tuple[float, dict]:
    """precios: {activo_id: precio_actual}. Si falta un activo, se usa su
    costo promedio (P&L no realizado = 0 para ese activo, a falta de dato)."""
    total = 0.0
    detalle = {}
    for (broker, activo_id), pos in estado.posiciones.items():
        cant = pos.cantidad
        if abs(cant) < 1e-9:
            continue
        precio = precios.get(activo_id, pos.costo_promedio)
        valor = cant * precio
        detalle[(broker, activo_id)] = valor
        total += valor
    return total, detalle


def pnl_no_realizado(estado: Estado, precios: dict) -> float:
    total = 0.0
    for (broker, activo_id), pos in estado.posiciones.items():
        cant = pos.cantidad
        if abs(cant) < 1e-9:
            continue
        precio = precios.get(activo_id, pos.costo_promedio)
        total += cant * (precio - pos.costo_promedio)
    return total


def valor_cartera_ars(estado: Estado, precios: dict, fecha_valuacion: str, serie_tc: dict) -> float:
    """Convierte cajas y posiciones a ARS al tipo de cambio de
    'fecha_valuacion' (normalmente hoy) — es una FOTO, no una serie
    histórica. precios: {activo_id: (precio, moneda)} o {activo_id: precio}
    asumiendo ARS si no se especifica moneda."""
    total = 0.0
    for (broker, moneda), saldo in estado.cajas.items():
        total += convertir_a_ars(saldo, moneda, fecha_valuacion, serie_tc)
    for (broker, activo_id), pos in estado.posiciones.items():
        cant = pos.cantidad
        if abs(cant) < 1e-9:
            continue
        p = precios.get(activo_id)
        if isinstance(p, tuple):
            precio, moneda_precio = p
        elif p is not None:
            precio, moneda_precio = p, (pos.lotes[0].moneda if pos.lotes else "ARS")
        else:
            precio, moneda_precio = pos.costo_promedio, (pos.lotes[0].moneda if pos.lotes else "ARS")
        total += convertir_a_ars(cant * precio, moneda_precio, fecha_valuacion, serie_tc)
    return total


def chequeo_identidad_ars(estado: Estado, precios: dict, serie_tc: dict,
                           fecha_valuacion: str, tolerancia: float = 1.0) -> dict:
    """La misma identidad de §3.4, pero convirtiendo todo a ARS — cada
    flujo histórico a SU propio tipo de cambio, y el valor de hoy al
    tipo de cambio de 'fecha_valuacion'. Requiere haber corrido
    recalcular(..., serie_tc=serie_tc)."""
    pnl_no_realizado_ars = 0.0
    for (broker, activo_id), pos in estado.posiciones.items():
        cant = pos.cantidad
        if abs(cant) < 1e-9 or not pos.lotes:
            continue
        moneda_pos = pos.lotes[0].moneda
        p = precios.get(activo_id)
        if isinstance(p, tuple):
            precio, moneda_precio = p
        elif p is not None:
            precio, moneda_precio = p, moneda_pos
        else:
            precio, moneda_precio = pos.costo_promedio, moneda_pos
        valor_mercado_ars = convertir_a_ars(cant * precio, moneda_precio, fecha_valuacion, serie_tc)
        costo_prom_ars = sum(l.cantidad * l.costo_unitario_ars for l in pos.lotes) / cant if cant else 0.0
        pnl_no_realizado_ars += valor_mercado_ars - cant * costo_prom_ars

    valor_cartera = valor_cartera_ars(estado, precios, fecha_valuacion, serie_tc)
    pnl_realizado_ars_total = sum(p.pnl_realizado_ars for p in estado.posiciones.values())

    esperado = (
        estado.capital_aportado_ars
        + estado.valor_apertura_ars
        + pnl_realizado_ars_total
        + pnl_no_realizado_ars
        + estado.renta_cobrada_ars
        - estado.comisiones_ars
        - estado.impuestos_ars
        + estado.transferencias_neto_ars
    )

    diferencia = valor_cartera - esperado
    return {
        "valor_cartera_ars": round(valor_cartera, 2),
        "esperado_ars": round(esperado, 2),
        "diferencia": round(diferencia, 2),
        "ok": abs(diferencia) < tolerancia,
    }


def chequeo_identidad(estado: Estado, precios: dict, tolerancia: float = 0.01) -> dict:
    """La identidad contable de §3.4 del guion. Sirve para la franja
    "todo en orden" del dashboard: si `ok` es False, hay un movimiento
    mal cargado (no es un problema del mercado)."""
    valor_cajas = sum(estado.cajas.values())
    valor_pos, _ = valor_posiciones(estado, precios)
    valor_cartera = valor_cajas + valor_pos

    esperado = (
        estado.capital_aportado
        + estado.valor_apertura
        + pnl_realizado_total(estado)
        + pnl_no_realizado(estado, precios)
        + estado.renta_cobrada
        - estado.comisiones
        - estado.impuestos
        + estado.transferencias_neto
    )

    diferencia = valor_cartera - esperado
    return {
        "valor_cartera": round(valor_cartera, 2),
        "esperado": round(esperado, 2),
        "diferencia": round(diferencia, 2),
        "ok": abs(diferencia) < tolerancia,
    }
