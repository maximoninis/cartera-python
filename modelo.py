"""Modelo de datos de la cartera: Movimiento y Activo.

Sin IO, sin dependencias externas. Un Movimiento es el único tipo de
registro que existe — todo lo demás (posiciones, cajas, P&L) se deriva
de una lista de Movimientos en motor.py.
"""
from dataclasses import dataclass, field
from typing import Optional

TIPOS_MOVIMIENTO = {
    "deposito", "retiro",
    "compra", "venta",
    "dividendo", "interes",
    "impuesto", "comision",
    "conversion",
    "apertura",
    "transferencia",
}

# Tipos que abren/aumentan una posición en un activo
TIPOS_APERTURA_POSICION = {"compra", "apertura"}


@dataclass
class Movimiento:
    id: str
    fecha: str                      # AAAA-MM-DD
    tipo: str
    broker: str
    moneda: str
    monto_neto: float               # impacto real en caja, CON signo
    fecha_liquidacion: Optional[str] = None
    activo_id: Optional[str] = None
    cantidad: float = 0.0           # positiva en compra/apertura, negativa en venta
    precio_unitario: float = 0.0
    monto_bruto: float = 0.0        # cantidad × precio, siempre positivo (solo precio, sin fees)
    comisiones: float = 0.0         # siempre positivo
    impuestos: float = 0.0          # siempre positivo
    cantidad_destino: Optional[float] = None   # solo 'conversion'
    moneda_destino: Optional[str] = None       # solo 'conversion'
    id_relacionado: Optional[str] = None       # solo 'transferencia'
    nota: str = ""
    huella: Optional[str] = None    # para deduplicación al importar
    fuente: str = "manual"          # 'manual' | nombre del importador (ej. 'cocos')

    def validar(self) -> list[str]:
        """Devuelve una lista de errores. Vacía = movimiento válido."""
        errores = []

        if self.tipo not in TIPOS_MOVIMIENTO:
            errores.append(f"tipo desconocido: '{self.tipo}'")
            return errores  # sin tipo válido no tiene sentido seguir validando

        if not self.fecha or len(self.fecha) != 10 or self.fecha[4] != "-" or self.fecha[7] != "-":
            errores.append(f"fecha con formato inválido (esperado AAAA-MM-DD): '{self.fecha}'")

        if self.comisiones < 0:
            errores.append("comisiones debe ser >= 0")
        if self.impuestos < 0:
            errores.append("impuestos debe ser >= 0")

        if self.tipo in TIPOS_APERTURA_POSICION:
            if not self.activo_id:
                errores.append(f"{self.tipo} requiere activo_id")
            if self.cantidad <= 0:
                errores.append(f"{self.tipo} requiere cantidad positiva (vino {self.cantidad})")

        elif self.tipo == "venta":
            if not self.activo_id:
                errores.append("venta requiere activo_id")
            if self.cantidad >= 0:
                errores.append(f"venta requiere cantidad negativa (vino {self.cantidad})")

        elif self.tipo == "conversion":
            if self.cantidad_destino is None or not self.moneda_destino:
                errores.append("conversion requiere cantidad_destino y moneda_destino")

        elif self.tipo == "transferencia":
            if not self.id_relacionado:
                errores.append("transferencia requiere id_relacionado")

        return errores

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def from_dict(d: dict) -> "Movimiento":
        return Movimiento(**d)


@dataclass
class Activo:
    id: str
    nombre: str
    clase: str                      # accion | cedear | bono | fci | cripto | moneda
    moneda_emision: str
    ticker_yahoo: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def from_dict(d: dict) -> "Activo":
        return Activo(**d)
