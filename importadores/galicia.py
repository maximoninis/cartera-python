"""Importador de Galicia (caja de ahorro en pesos y en dólares).

A diferencia de Cocos, la cuenta de Galicia mezcla gastos personales con
operaciones de inversión. Por eso este importador NO intenta registrar
todo el resumen — solo las filas relacionadas con la cartera:

    SUSCRIPCION FIMA / RESCATE FIMA        -> compra / venta de FCI
    COMP. TITULOS / VENTA DE TITULOS       -> compra / venta de bonos
    COMISION Y DERECHOS DE MERCADO         -> comisión de esa compra
    Compra venta de dolares                -> conversion ARS<->USD
    INTERES CAPITALIZADO / RENDIMIENTO USD -> interés de la caja

Todo lo demás (compras con débito, transferencias a terceros, sueldo,
pago de servicios, etc.) se ignora: es vida personal, no cartera.

Regla de negocio CONFIRMADA por el usuario (13/09/2026): como no hay
forma de saber, mirando el resumen, qué plata era "para invertir" y
cuál era de uso personal, cada compra de FCI o bono se empareja con un
'deposito' implícito por el mismo monto en la misma fecha. Esto hace
que "capital aportado" en la identidad contable represente el total
histórico invertido desde Galicia, no un ahorro extra por encima del
gasto normal.

LIMITACIÓN CONOCIDA: el resumen bancario no informa la cantidad de
cuotapartes/nominales de cada operación de FIMA o bono, solo el monto
en pesos. Como parche hasta integrar las fuentes de cotización reales
(paso 4 del guion — argentinadatos para FCI, yfinance para bonos), se
usa el propio monto como "cantidad" con precio_unitario=1. Esto deja el
costo básico correcto, pero el valor de mercado de estas posiciones va
a quedar pegado al costo hasta que se reemplace por datos reales.
"""
import re
from datetime import datetime

from modelo import Movimiento

CAMPOS_FILA = {"moneda", "fecha", "text"}

PALABRAS_CLAVE = (
    "SUSCRIPCION FIMA", "RESCATE FIMA",
    "COMP. TITULOS", "VENTA DE TITULOS",
    "COMISION Y DERECHOS",
    "Compra venta de dolares",
    "INTERES CAPITALIZADO", "RENDIMIENTO USD",
)

_num_re = re.compile(r"-?[\d\.]+,\d{2}")
_op_re = re.compile(r"OPERACION[:\s]+(\S+)", re.IGNORECASE)
_nro_op_re = re.compile(r"Nro Operaci[oó]n:?\s*(\S+)", re.IGNORECASE)


def detectar(filas: list[dict]) -> bool:
    return bool(filas) and CAMPOS_FILA.issubset(set(filas[0].keys()))


def leer_pdf(ruta: str) -> list[dict]:
    """Extrae filas {moneda, fecha, text} de un resumen de Galicia (PDF,
    pueden venir varios resúmenes mensuales concatenados)."""
    import pdfplumber

    with pdfplumber.open(ruta) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    date_re = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.*)$")
    moneda = None
    rows = []
    for pg in pages:
        lines = pg.split("\n")
        if lines and "Caja de Ahorro en Pesos" in lines[0]:
            moneda = "ARS"
        elif lines and "Caja de Ahorro en dolares" in lines[0]:
            moneda = "USD"
        in_movs = False
        buf = None
        for line in lines:
            if line.strip().startswith("Fecha Descripción"):
                in_movs = True
                continue
            if not in_movs:
                continue
            if line.strip().startswith("Total") or line.strip().startswith("Los depósitos"):
                in_movs = False
                if buf:
                    rows.append(buf)
                buf = None
                continue
            m = date_re.match(line)
            if m:
                if buf:
                    rows.append(buf)
                buf = {"moneda": moneda, "fecha": m.group(1), "text": m.group(2)}
            elif buf is not None:
                buf["text"] += " | " + line.strip()
        if buf:
            rows.append(buf)
    return rows


def _fecha(s: str) -> str:
    return datetime.strptime(s.strip(), "%d/%m/%y").strftime("%Y-%m-%d")


def _numeros(texto: str) -> list[float]:
    crudo = texto.split("|")[0]
    return [float(n.replace(".", "").replace(",", ".")) for n in _num_re.findall(crudo)]


def _huella(fecha: str, texto: str) -> str:
    """Huella estable: NO depende de en qué archivo ni en qué posición
    aparece la fila, para poder volver a subir un PDF con meses
    superpuestos sin duplicar movimientos. Usa el número de operación
    del banco cuando existe; si no, fecha + primeras palabras + monto."""
    m_op = _nro_op_re.search(texto) or _op_re.search(texto)
    if m_op:
        return f"galicia-op-{m_op.group(1)}"
    numeros = _numeros(texto)
    monto = numeros[-2] if len(numeros) >= 2 else 0.0
    primeras_palabras = re.sub(r"\s+", " ", texto.split("|")[0]).strip()[:40]
    return f"galicia-{fecha}-{primeras_palabras}-{monto}"


def _nro_operacion(texto: str) -> str | None:
    m = _nro_op_re.search(texto) or _op_re.search(texto)
    return m.group(1) if m else None


def _operaciones_titulos_conversion(filas: list[dict]) -> set[str]:
    """Detecta compras/ventas de bonos que en realidad son una conversión
    de moneda disfrazada: el mismo Nro Operación aparece una vez como
    'COMP. TITULOS' en una moneda y otra vez como 'VENTA DE TITULOS' en
    la otra (comprar un bono en pesos y venderlo el mismo día en
    dólares es la forma clásica de "MEP por bonos" — no es que el
    usuario se quedó con el bono)."""
    por_operacion: dict[str, set[tuple[str, str]]] = {}
    for fila in filas:
        texto = fila["text"]
        if "COMP. TITULOS" in texto:
            tipo = "compra"
        elif "VENTA DE TITULOS" in texto:
            tipo = "venta"
        else:
            continue
        op = _nro_operacion(texto)
        if not op:
            continue
        por_operacion.setdefault(op, set()).add((tipo, fila["moneda"]))

    return {
        op for op, patas in por_operacion.items()
        if len(patas) == 2 and len({m for _, m in patas}) == 2  # dos monedas distintas
    }


def _procesar_conversion(pendientes: dict, clave: str, fecha: str, moneda: str, monto: float, nota: str) -> dict:
    """Empareja las dos patas (ARS y USD) de una misma operación de
    conversión — sea 'Compra venta de dolares' o un bono usado como
    vehículo de MEP — y arma el movimiento 'conversion' cuando llega
    la segunda pata."""
    pata = pendientes.pop(clave, None)
    if pata is None:
        pendientes[clave] = {"fecha": fecha, "moneda": moneda, "monto": monto}
        return {"fila": -1, "estado": "pendiente_par", "motivo": f"{clave}, esperando la otra pata"}

    patas = [pata, {"fecha": fecha, "moneda": moneda, "monto": monto}]
    origen = next(p for p in patas if p["monto"] < 0)
    destino = next(p for p in patas if p["monto"] >= 0)
    mov = Movimiento(
        id=f"gal-conv-{clave}", fecha=origen["fecha"], broker="galicia",
        moneda=origen["moneda"], monto_neto=origen["monto"],
        cantidad_destino=destino["monto"], moneda_destino=destino["moneda"],
        tipo="conversion", huella=f"gal-conv-{clave}", fuente="galicia", nota=nota,
    )
    errores = mov.validar()
    return {"fila": -1, "estado": "ok" if not errores else "rechazado",
            "motivo": "; ".join(errores), "movimientos": [mov.to_dict()] if not errores else []}


def interpretar(filas: list[dict]) -> list[dict]:
    candidatos = []
    conversiones_pendientes: dict[str, dict] = {}
    conversiones_por_titulos = _operaciones_titulos_conversion(filas)

    for i, fila in enumerate(filas):
        texto = fila["text"]
        fecha = _fecha(fila["fecha"])
        moneda = fila["moneda"]

        if not any(k in texto for k in PALABRAS_CLAVE):
            candidatos.append({"fila": i, "estado": "ignorado", "motivo": "movimiento personal, fuera de la cartera"})
            continue

        numeros = _numeros(texto)
        if len(numeros) < 2:
            candidatos.append({"fila": i, "estado": "rechazado", "motivo": f"no se pudo leer el monto: {texto[:80]}"})
            continue
        monto = numeros[-2]  # penúltimo número = monto del movimiento; último = saldo

        huella = _huella(fecha, texto)
        base = dict(fecha=fecha, broker="galicia", moneda=moneda,
                    huella=huella, fuente="galicia", nota=texto[:120])
        id_base = f"gal-{huella}"

        if "SUSCRIPCION FIMA" in texto:
            fondo = fila["text"].split("|")[1].strip() if "|" in fila["text"] else "FIMA"
            monto_abs = abs(monto)
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base + "-aporte", tipo="deposito", monto_neto=monto_abs).to_dict(),
                Movimiento(**base, id=id_base, activo_id=fondo, tipo="compra",
                           cantidad=monto_abs, precio_unitario=1.0, monto_bruto=monto_abs,
                           monto_neto=monto).to_dict(),
            ]})

        elif "RESCATE FIMA" in texto:
            fondo = fila["text"].split("|")[1].strip() if "|" in fila["text"] else "FIMA"
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base, activo_id=fondo, tipo="venta",
                           cantidad=-monto, precio_unitario=1.0, monto_bruto=monto,
                           monto_neto=monto).to_dict(),
            ]})

        elif "COMP. TITULOS" in texto and _nro_operacion(texto) in conversiones_por_titulos:
            candidatos.append(_procesar_conversion(
                conversiones_pendientes, "titulos-" + _nro_operacion(texto), fecha, moneda, monto,
                nota=f"compra/venta de {fila['text'].split('|')[1].strip() if '|' in fila['text'] else 'bono'} como MEP",
            ))

        elif "VENTA DE TITULOS" in texto and _nro_operacion(texto) in conversiones_por_titulos:
            candidatos.append(_procesar_conversion(
                conversiones_pendientes, "titulos-" + _nro_operacion(texto), fecha, moneda, monto,
                nota=f"compra/venta de {fila['text'].split('|')[1].strip() if '|' in fila['text'] else 'bono'} como MEP",
            ))

        elif "COMP. TITULOS" in texto:
            bono = fila["text"].split("|")[1].strip() if "|" in fila["text"] else "BONO"
            monto_abs = abs(monto)
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base + "-aporte", tipo="deposito", monto_neto=monto_abs).to_dict(),
                Movimiento(**base, id=id_base, activo_id=bono, tipo="compra",
                           cantidad=monto_abs, precio_unitario=1.0, monto_bruto=monto_abs,
                           monto_neto=monto).to_dict(),
            ]})

        elif "VENTA DE TITULOS" in texto:
            bono = fila["text"].split("|")[1].strip() if "|" in fila["text"] else "BONO"
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base, activo_id=bono, tipo="venta",
                           cantidad=-monto, precio_unitario=1.0, monto_bruto=monto,
                           monto_neto=monto).to_dict(),
            ]})

        elif "COMISION Y DERECHOS" in texto:
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base, tipo="comision", comisiones=abs(monto), monto_neto=monto).to_dict(),
            ]})

        elif "INTERES CAPITALIZADO" in texto or "RENDIMIENTO USD" in texto:
            candidatos.append({"fila": i, "estado": "ok", "movimientos": [
                Movimiento(**base, id=id_base, tipo="interes", monto_neto=monto).to_dict(),
            ]})

        elif "Compra venta de dolares" in texto:
            m_op = _op_re.search(texto)
            op_id = m_op.group(1) if m_op else f"sinop-{fecha}-{i}"
            candidatos.append(_procesar_conversion(
                conversiones_pendientes, "dolares-" + op_id, fecha, moneda, monto,
                nota=f"compra/venta de dólares, operación {op_id}",
            ))

    if conversiones_pendientes:
        for op_id, pata in conversiones_pendientes.items():
            candidatos.append({"fila": -1, "estado": "rechazado",
                                "motivo": f"operación {op_id} sin la otra pata (¿PDF incompleto?)"})

    return candidatos
