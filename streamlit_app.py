"""Cartera personal — versión Streamlit.

Corre en una sola app, un solo lenguaje: usa motor.py y los
importadores de Python (importadores/cocos.py, importadores/galicia.py)
directamente, sin traducir nada a JavaScript. Pensada para correr en
Streamlit Community Cloud (gratis) — ver README.md para el paso a paso
de despliegue.

Local: streamlit run streamlit_app.py
"""
import csv
import io
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modelo import Movimiento
from motor import buscar_tc, chequeo_identidad_ars, convertir_a_ars, recalcular
from importadores import cocos as imp_cocos
from importadores import galicia as imp_galicia
from importadores.utils import fusionar

RAIZ = Path(__file__).parent
DATOS = RAIZ / "datos"

st.set_page_config(page_title="Cartera personal", page_icon="💼", layout="wide")


# ==================================================================== estilo
def inyectar_css():
    st.markdown(
        """
        <style>
        :root {
            --accent: #0071e3;
            --pos: #1e8e3e;
            --neg: #d93025;
        }
        .bloque-hero {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 28px 32px;
            margin-bottom: 8px;
        }
        .bloque-hero .etiqueta { font-size: 13px; opacity: 0.6; margin-bottom: 4px; }
        .bloque-hero .numero { font-size: 42px; font-weight: 600; letter-spacing: -0.02em; }
        .tc-linea { font-size: 12px; opacity: 0.55; margin-top: 4px; }
        .tarjeta-pos {
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 14px 18px;
            margin-bottom: 8px;
        }
        .tarjeta-pos .nombre { font-size: 16px; font-weight: 600; }
        .tarjeta-pos .detalle { font-size: 12px; opacity: 0.55; }
        .tag-estado {
            display: inline-block; padding: 2px 10px; border-radius: 999px;
            font-size: 11px; font-weight: 600;
        }
        .tag-ok { background: rgba(30,142,62,0.15); color: #4caf6e; }
        .tag-ignorado { background: rgba(255,255,255,0.08); color: #999; }
        .tag-revisar { background: rgba(201,162,39,0.18); color: #d4af37; }
        .tag-rechazado { background: rgba(217,48,37,0.15); color: #e57373; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt(n: float, decimales: int = 2) -> str:
    if n is None:
        return "—"
    return f"{n:,.{decimales}f}".replace(",", "@").replace(".", ",").replace("@", ".")


# ==================================================================== datos
def cargar_json(ruta: Path) -> dict:
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return {}


def cargar_movimientos_default() -> list[dict]:
    return cargar_json(DATOS / "movimientos.json") or []


def inicializar_estado():
    if "movimientos" not in st.session_state:
        st.session_state.movimientos = cargar_movimientos_default()
    if "valores_manual" not in st.session_state:
        conocidos = cargar_json(DATOS / "valores_conocidos.json")
        st.session_state.valores_manual = {k: v for k, v in conocidos.items() if not k.startswith("_")}
    if "snapshots_rendimiento" not in st.session_state:
        st.session_state.snapshots_rendimiento = []
    if "moneda_vista" not in st.session_state:
        st.session_state.moneda_vista = "ARS"
    if "candidatos_pendientes" not in st.session_state:
        st.session_state.candidatos_pendientes = []


def serie_tc() -> dict:
    return cargar_json(DATOS / "tipos_de_cambio.json")


def movimientos_objetos() -> list[Movimiento]:
    return [Movimiento.from_dict(d) for d in st.session_state.movimientos]


def fecha_hoy_tc(serie: dict) -> str | None:
    return max(serie) if serie else None


# ============================================================ carga/descarga
def descargar_estado_button():
    paquete = {
        "movimientos": st.session_state.movimientos,
        "valores_manual": st.session_state.valores_manual,
        "snapshots_rendimiento": st.session_state.snapshots_rendimiento,
    }
    st.download_button(
        "⬇️ Descargar mi cartera (para guardarla o retomarla después)",
        data=json.dumps(paquete, ensure_ascii=False, indent=2),
        file_name=f"cartera-{date.today().isoformat()}.json",
        mime="application/json",
        use_container_width=False,
    )


def restaurar_estado_uploader():
    archivo = st.file_uploader(
        "Restaurar una sesión guardada antes (el archivo que bajaste con el botón de arriba)",
        type=["json"], key="restaurar_json",
    )
    if archivo is not None:
        try:
            paquete = json.load(archivo)
            st.session_state.movimientos = paquete.get("movimientos", st.session_state.movimientos)
            st.session_state.valores_manual = paquete.get("valores_manual", st.session_state.valores_manual)
            st.session_state.snapshots_rendimiento = paquete.get("snapshots_rendimiento", st.session_state.snapshots_rendimiento)
            st.success(f"Restaurado: {len(st.session_state.movimientos)} movimientos.")
        except Exception as e:
            st.error(f"No pude leer ese archivo: {e}")


# ==================================================================== main
def main():
    inyectar_css()
    inicializar_estado()

    st.title("💼 Cartera personal")

    col_titulo, col_toggle = st.columns([3, 1])
    with col_toggle:
        st.session_state.moneda_vista = st.radio(
            "Ver en", ["ARS", "USD"], horizontal=True, label_visibility="collapsed",
            index=0 if st.session_state.moneda_vista == "ARS" else 1,
        )

    tc = serie_tc()
    fecha_hoy = fecha_hoy_tc(tc)

    tab_cartera, tab_evolucion, tab_movimientos = st.tabs(["📊 Cartera", "📈 Evolución", "📋 Movimientos"])

    with tab_cartera:
        vista_cartera(tc, fecha_hoy)

    with tab_evolucion:
        vista_evolucion(tc, fecha_hoy)

    with tab_movimientos:
        vista_movimientos(tc, fecha_hoy)


# ============================================================== tab Cartera
def valor_conocido_ars(clave: str, costo_ars_default: float) -> float:
    if clave in st.session_state.valores_manual:
        return float(st.session_state.valores_manual[clave])
    return costo_ars_default


def vista_cartera(tc: dict, fecha_hoy: str | None):
    movs = movimientos_objetos()
    estado = recalcular(movs, serie_tc=tc if tc else None)
    moneda_vista = st.session_state.moneda_vista

    def conv_vista(monto_ars: float) -> float:
        if moneda_vista == "ARS" or not fecha_hoy:
            return monto_ars
        t = buscar_tc(fecha_hoy, tc)
        return monto_ars / t if t else monto_ars

    total_invertido_ars = 0.0
    total_efectivo_ars = 0.0

    posiciones_por_broker: dict[str, list] = {}
    for (broker, activo_id), pos in estado.posiciones.items():
        cant = pos.cantidad
        if abs(cant) < 1e-6:
            continue
        posiciones_por_broker.setdefault(broker, []).append((activo_id, pos, cant))

    cajas_por_broker: dict[str, list] = {}
    for (broker, moneda), saldo in estado.cajas.items():
        if broker == "galicia" and moneda == "ARS":
            continue  # no representa un saldo real, ver README
        cajas_por_broker.setdefault(broker, []).append((moneda, saldo))

    brokers = sorted(set(posiciones_por_broker) | set(cajas_por_broker))

    for broker in brokers:
        st.markdown(f"**{broker.capitalize()}**")
        for activo_id, pos, cant in posiciones_por_broker.get(broker, []):
            moneda_pos = pos.lotes[0].moneda if pos.lotes else "ARS"
            costo_total = cant * pos.costo_promedio
            costo_ars = convertir_a_ars(costo_total, moneda_pos, fecha_hoy, tc) if fecha_hoy else costo_total
            clave = f"{broker}|{activo_id}"
            valor_ars_actual = valor_conocido_ars(clave, costo_ars)

            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.markdown(
                    f'<div class="tarjeta-pos"><div class="nombre">{activo_id}</div>'
                    f'<div class="detalle">{fmt(cant, 0 if cant % 1 == 0 else 2)} nominales (según el historial)</div></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                nuevo_valor = st.number_input(
                    "Valor de hoy (ARS)", value=float(valor_ars_actual), step=100.0,
                    key=f"valor_{clave}", format="%.2f",
                )
                if nuevo_valor != valor_ars_actual:
                    st.session_state.valores_manual[clave] = nuevo_valor
                    valor_ars_actual = nuevo_valor
            with c3:
                st.markdown(
                    f'<div style="text-align:right;padding-top:28px;font-size:18px;font-weight:600;">'
                    f'{"$" if moneda_vista == "ARS" else "US$"} {fmt(conv_vista(valor_ars_actual))}</div>',
                    unsafe_allow_html=True,
                )
            total_invertido_ars += valor_ars_actual

        for moneda, saldo in cajas_por_broker.get(broker, []):
            saldo_ars = convertir_a_ars(saldo, moneda, fecha_hoy, tc) if fecha_hoy else saldo
            total_efectivo_ars += saldo_ars
            c1, c2 = st.columns([5, 2])
            with c1:
                st.markdown(
                    f'<div class="tarjeta-pos"><div class="nombre">Efectivo ({moneda})</div>'
                    f'<div class="detalle">Disponible para invertir o retirar</div></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f'<div style="text-align:right;padding-top:14px;font-size:18px;font-weight:600;">'
                    f'{"$" if moneda_vista == "ARS" else "US$"} {fmt(conv_vista(saldo_ars))}</div>',
                    unsafe_allow_html=True,
                )

    total_general = total_invertido_ars + total_efectivo_ars

    tc_hoy = buscar_tc(fecha_hoy, tc) if fecha_hoy else None
    st.markdown(
        f"""
        <div class="bloque-hero">
          <div class="etiqueta">Valor total</div>
          <div class="numero">{'$' if moneda_vista == 'ARS' else 'US$'} {fmt(conv_vista(total_general))}</div>
          <div class="tc-linea">{'Cotización usada: $' + fmt(tc_hoy, 2) + ' ARS/USD (' + fecha_hoy + ')' if tc_hoy else 'Sin cotización cargada'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "La cantidad de nominales viene del historial de movimientos y puede estar vieja — "
        "es solo informativa. Lo que manda para el total es 'Valor de hoy', que cargás vos "
        "(copiado directo de la app de tu broker, siempre en pesos)."
    )

    with st.expander("¿Todo en orden? (chequeo contable del historial de movimientos)"):
        precios_vacio: dict = {}
        chequeo = chequeo_identidad_ars(estado, precios_vacio, tc, fecha_hoy) if fecha_hoy else None
        if chequeo:
            ok = chequeo["ok"]
            st.write(
                ("✅ " if ok else "⚠️ ") +
                f"Valor esperado según el historial: ${fmt(chequeo['esperado_ars'])} — "
                f"valor a costo de las cajas y posiciones: ${fmt(chequeo['valor_cartera_ars'])} — "
                f"diferencia: ${fmt(chequeo['diferencia'])}."
            )
            if not ok:
                st.caption(
                    "No cierra al centavo — normal si solo tenés algunas cotizaciones de dólar cargadas "
                    "en vez de una serie diaria completa (ver tipos_de_cambio.json). No es un problema "
                    "con 'Valor de hoy': este chequeo mira el historial de movimientos a costo, no lo "
                    "que cargaste a mano arriba."
                )
        else:
            st.caption("No hay tipo de cambio cargado, no se puede correr el chequeo.")


# ============================================================= tab Evolución
def capital_invertido_ars(estado) -> float:
    return (
        estado.capital_aportado_ars + estado.valor_apertura_ars
        + sum(p.pnl_realizado_ars for p in estado.posiciones.values())
        + estado.renta_cobrada_ars - estado.comisiones_ars - estado.impuestos_ars
        + estado.transferencias_neto_ars
    )


def historial_costo(movs: list[Movimiento], tc: dict) -> pd.DataFrame:
    if not tc or not movs:
        return pd.DataFrame(columns=["fecha", "valor_ars"])
    fecha_min = min(m.fecha for m in movs)
    fecha_max = max(tc)
    d = date(int(fecha_min[:4]), int(fecha_min[5:7]), 1)
    fin = date(int(fecha_max[:4]), int(fecha_max[5:7]), int(fecha_max[8:10]))
    fechas = []
    while d <= fin:
        fechas.append(d.isoformat())
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    if not fechas or fechas[-1] != fecha_max:
        fechas.append(fecha_max)

    filas = []
    for f in fechas:
        est = recalcular(movs, hasta=f, serie_tc=tc)
        filas.append({"fecha": f, "valor_ars": capital_invertido_ars(est)})
    return pd.DataFrame(filas)


def vista_evolucion(tc: dict, fecha_hoy: str | None):
    movs = movimientos_objetos()
    moneda_vista = st.session_state.moneda_vista

    st.subheader("Capital invertido en el tiempo")
    st.caption("Calculado con certeza a partir de tu historial de movimientos — no depende de precios de mercado.")

    df = historial_costo(movs, tc)
    if not df.empty:
        c1, c2 = st.columns(2)
        desde = c1.date_input("Desde", value=date(2026, 1, 1), key="ev_desde")
        hasta = c2.date_input("Hasta", value=datetime.strptime(df["fecha"].iloc[-1], "%Y-%m-%d").date(), key="ev_hasta")
        df_filtrado = df[(df["fecha"] >= desde.isoformat()) & (df["fecha"] <= hasta.isoformat())].copy()

        if moneda_vista == "USD":
            df_filtrado["valor"] = df_filtrado.apply(
                lambda r: r["valor_ars"] / buscar_tc(r["fecha"], tc) if buscar_tc(r["fecha"], tc) else r["valor_ars"], axis=1
            )
        else:
            df_filtrado["valor"] = df_filtrado["valor_ars"]

        df_chart = df_filtrado.set_index("fecha")[["valor"]]
        df_chart.columns = [f"Capital invertido ({moneda_vista})"]
        st.line_chart(df_chart)
    else:
        st.info("Todavía no hay suficiente historial con cotización para graficar.")

    st.divider()
    st.subheader("Rendimiento real")
    st.caption("Se arma desde hoy: cada vez que guardás una foto con los valores de la pestaña Cartera, queda un punto más.")

    snaps = st.session_state.snapshots_rendimiento
    if len(snaps) < 2:
        st.info(f"{'Ninguna foto guardada todavía' if not snaps else '1 foto guardada'} — guardá al menos dos para ver el gráfico.")
    else:
        df_snap = pd.DataFrame(snaps)
        base_ars, base_usd = df_snap.iloc[0]["valor_ars"], df_snap.iloc[0]["valor_usd"]
        df_snap["Tu cartera (%)"] = 100 * (df_snap["valor_ars"] / base_ars - 1) if moneda_vista == "ARS" \
            else 100 * (df_snap["valor_usd"] / base_usd - 1)
        columnas = ["Tu cartera (%)"]
        con_spy = df_snap.dropna(subset=["spy"])
        if len(con_spy) >= 2:
            base_spy = con_spy.iloc[0]["spy"]
            df_snap["SPY (%)"] = 100 * (df_snap["spy"] / base_spy - 1)
            columnas.append("SPY (%)")
        st.line_chart(df_snap.set_index("fecha")[columnas])

    with st.form("form_snapshot"):
        spy_hoy = st.number_input("Precio de SPY hoy (USD, opcional — para comparar)", min_value=0.0, step=0.01)
        guardar = st.form_submit_button("📸 Guardar foto de hoy")
        if guardar:
            movs2 = movimientos_objetos()
            estado = recalcular(movs2, serie_tc=tc if tc else None)
            total_ars = 0.0
            for (broker, activo_id), pos in estado.posiciones.items():
                cant = pos.cantidad
                if abs(cant) < 1e-6:
                    continue
                moneda_pos = pos.lotes[0].moneda if pos.lotes else "ARS"
                costo_ars = convertir_a_ars(cant * pos.costo_promedio, moneda_pos, fecha_hoy, tc) if fecha_hoy else 0
                total_ars += valor_conocido_ars(f"{broker}|{activo_id}", costo_ars)
            for (broker, moneda), saldo in estado.cajas.items():
                if broker == "galicia" and moneda == "ARS":
                    continue
                total_ars += convertir_a_ars(saldo, moneda, fecha_hoy, tc) if fecha_hoy else saldo
            tc_hoy_val = buscar_tc(fecha_hoy, tc) if fecha_hoy else None
            hoy = date.today().isoformat()
            nuevo = {"fecha": hoy, "valor_ars": total_ars, "valor_usd": (total_ars / tc_hoy_val if tc_hoy_val else None),
                     "spy": spy_hoy if spy_hoy > 0 else None}
            snaps = [s for s in st.session_state.snapshots_rendimiento if s["fecha"] != hoy]
            snaps.append(nuevo)
            st.session_state.snapshots_rendimiento = sorted(snaps, key=lambda s: s["fecha"])
            st.success(f"Guardado — {len(st.session_state.snapshots_rendimiento)} fotos en total.")
            st.rerun()


# ============================================================ tab Movimientos
def leer_csv_generico(texto: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def normalizar_candidatos(candidatos: list[dict]) -> list[dict]:
    salida = []
    for c in candidatos:
        if c.get("movimiento"):
            salida.append({"estado": c["estado"], "movimiento": c["movimiento"], "motivo": c.get("motivo") or c.get("tipo_operacion_original", "")})
        elif c.get("movimientos"):
            for m in c["movimientos"]:
                salida.append({"estado": c["estado"], "movimiento": m, "motivo": c.get("motivo", "")})
    return salida


def vista_movimientos(tc: dict, fecha_hoy: str | None):
    st.subheader("Cargar movimientos")

    subtab_archivo, subtab_manual = st.tabs(["📤 Subir archivo", "✍️ Cargar a mano"])

    with subtab_archivo:
        archivo = st.file_uploader("CSV o PDF de tu broker/banco", type=["csv", "pdf"], key="uploader_movs")
        if archivo is not None:
            procesar_archivo_subido(archivo)

    with subtab_manual:
        formulario_manual()

    if st.session_state.candidatos_pendientes:
        mostrar_vista_previa()

    st.divider()
    st.subheader("Todos los movimientos")
    df = pd.DataFrame(st.session_state.movimientos)
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        f_broker = c1.selectbox("Broker", ["(todos)"] + sorted(df["broker"].dropna().unique().tolist()))
        f_tipo = c2.selectbox("Tipo", ["(todos)"] + sorted(df["tipo"].dropna().unique().tolist()))
        f_activo = c3.selectbox("Activo", ["(todos)"] + sorted(df["activo_id"].dropna().unique().tolist()))
        filtrado = df.copy()
        if f_broker != "(todos)":
            filtrado = filtrado[filtrado["broker"] == f_broker]
        if f_tipo != "(todos)":
            filtrado = filtrado[filtrado["tipo"] == f_tipo]
        if f_activo != "(todos)":
            filtrado = filtrado[filtrado["activo_id"] == f_activo]
        columnas = ["fecha", "broker", "tipo", "activo_id", "cantidad", "moneda", "monto_neto", "nota"]
        st.dataframe(filtrado[columnas].sort_values("fecha", ascending=False), use_container_width=True, hide_index=True)
        st.caption(f"{len(filtrado)} movimientos")
    else:
        st.info("Todavía no hay movimientos cargados.")

    st.divider()
    descargar_estado_button()
    restaurar_estado_uploader()


def procesar_archivo_subido(archivo):
    nombre = archivo.name.lower()
    if nombre.endswith(".csv"):
        texto = archivo.read().decode("utf-8-sig")
        filas = leer_csv_generico(texto)
        if imp_cocos.detectar(filas):
            candidatos = imp_cocos.interpretar(filas)
            st.session_state.candidatos_pendientes = normalizar_candidatos(candidatos)
            st.success(f"{archivo.name}: reconocido como Cocos. Revisá la vista previa abajo.")
        else:
            st.warning(f"{archivo.name}: no reconozco este formato de CSV todavía. Mandámelo por chat y te armo el lector.")
    elif nombre.endswith(".pdf"):
        filas = imp_galicia.leer_pdf(archivo)
        if filas:
            candidatos = imp_galicia.interpretar(filas)
            st.session_state.candidatos_pendientes = normalizar_candidatos(candidatos)
            st.success(f"{archivo.name}: procesado como resumen de Galicia. Revisá la vista previa abajo.")
        else:
            st.warning(f"{archivo.name}: no pude leer ningún movimiento de este PDF. Mandámelo por chat así lo reviso.")
    else:
        st.warning(f"{archivo.name}: todavía no leo este formato (Excel/imágenes). Mandámelo por chat mientras tanto.")


def formulario_manual():
    with st.form("form_manual", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=date.today())
        broker = c2.text_input("Broker", placeholder="ej. balanz")
        tipo = c3.selectbox("Tipo", [
            "compra", "venta", "deposito", "retiro", "dividendo", "interes",
            "comision", "impuesto", "apertura",
        ])
        c4, c5, c6, c7 = st.columns(4)
        activo = c4.text_input("Activo (si aplica)")
        cantidad = c5.number_input("Cantidad (si aplica)", value=0.0, step=0.0001, format="%.4f")
        moneda = c6.selectbox("Moneda", ["ARS", "USD"])
        monto = c7.number_input("Monto (con signo)", value=0.0, step=0.01, format="%.2f")
        nota = st.text_input("Nota (opcional)")
        agregar = st.form_submit_button("Agregar a la vista previa")

        if agregar:
            huella = f"manual-{broker}-{fecha.isoformat()}-{tipo}-{datetime.now().timestamp()}"
            mov = Movimiento(
                id=huella, fecha=fecha.isoformat(), tipo=tipo, broker=broker.strip().lower() or "sin-especificar",
                activo_id=activo.strip() or None, cantidad=cantidad, moneda=moneda,
                monto_bruto=abs(monto), monto_neto=monto, huella=huella, fuente="manual", nota=nota,
            )
            errores = mov.validar()
            st.session_state.candidatos_pendientes.append({
                "estado": "rechazado" if errores else "ok",
                "movimiento": mov.to_dict(),
                "motivo": "; ".join(errores),
            })
            st.rerun()


def mostrar_vista_previa():
    st.subheader("Vista previa")
    candidatos = st.session_state.candidatos_pendientes
    por_estado: dict[str, int] = {}
    for c in candidatos:
        por_estado[c["estado"]] = por_estado.get(c["estado"], 0) + 1
    st.caption(", ".join(f"{v} {k}" for k, v in por_estado.items()))

    for c in candidatos:
        m = c["movimiento"]
        st.markdown(
            f'<span class="tag-estado tag-{c["estado"]}">{c["estado"]}</span> '
            f'{m["fecha"]} · {m["tipo"]} · {m.get("activo_id") or "—"} · '
            f'{fmt(m["monto_neto"])} {m["moneda"]} · {c.get("motivo") or m.get("nota") or ""}',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    if c1.button("✅ Agregar a mi cartera"):
        nuevos = [c["movimiento"] for c in candidatos if c["estado"] == "ok"]
        fusionados, agregados = fusionar(st.session_state.movimientos, nuevos)
        st.session_state.movimientos = fusionados
        st.session_state.candidatos_pendientes = []
        st.success(f"Se agregaron {agregados} movimientos nuevos.")
        st.rerun()
    if c2.button("❌ Descartar"):
        st.session_state.candidatos_pendientes = []
        st.rerun()


if __name__ == "__main__":
    main()
