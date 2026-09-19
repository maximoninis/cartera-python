# Cartera personal

Seguimiento de cartera de inversiones (Cocos, Galicia, y lo que sumes
después) — cartera de hoy, evolución en el tiempo, y carga de
movimientos nuevos subiendo el reporte del broker/banco.

## Por qué Streamlit (y no la versión HTML de antes)

Hubo una versión anterior como un solo archivo HTML, pensada para
abrir con doble clic sin instalar nada. Se abandonó por dos motivos
reales, no por gusto:

1. **Duplicaba toda la lógica de cálculo en dos lenguajes** (Python
   para vos, JavaScript para que corriera en el navegador). Dos
   copias de la misma cuenta que se podían desalinear.
2. **Se rompió** por una restricción de los navegadores con archivos
   abiertos con doble clic (`file://`) — cargar varios scripts locales
   sueltos podía fallar en silencio y tirar abajo toda la página.

Esta versión usa `motor.py` y los importadores de Python
(`importadores/cocos.py`, `importadores/galicia.py`) **directamente**,
sin traducir nada — una sola fuente de verdad. A cambio, hace falta
correr un comando para prenderla (local) o colgarla en un hosting
gratuito (para tenerla siempre disponible, desde cualquier
dispositivo). Ver la sección de despliegue más abajo.

## Estado actual

- **304 movimientos** cargados: Cocos completo (2024 a la fecha) y
  Galicia (solo lo relacionado a inversión).
- **Los valores de la pestaña Cartera reflejan tu foto real** de Cocos
  (17/09/2026) y Galicia confirmado — no el cálculo automático a
  partir de movimientos, que había quedado desactualizado (te
  faltaban semanas sin cargar, por eso SPY daba 51 nominales en vez de
  109). Esto vive en `datos/valores_conocidos.json` y en el campo
  "Valor de hoy" de cada posición — actualizalo cuando quieras
  resincronizar con la realidad.
- La cantidad de nominales que se ve en cada tarjeta sigue viniendo
  del historial de movimientos y puede estar vieja — es solo
  informativa, no afecta el total.

## Correrla en tu computadora (para probar antes de colgarla)

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Se abre sola en el navegador, en `http://localhost:8501`.

## Colgarla gratis, accesible desde cualquier dispositivo (Streamlit Community Cloud)

Un solo despliegue, después queda con una URL fija. Paso a paso:

1. **Creá una cuenta en GitHub** (gratis) si no tenés una:
   https://github.com/signup
2. **Creá un repositorio nuevo** (podés dejarlo privado) y subí todo
   el contenido de esta carpeta. La forma más simple, sin usar la
   terminal: en la página del repo, "Add file" → "Upload files", y
   arrastrás todo.
3. Andá a https://share.streamlit.io y entrá con tu cuenta de GitHub.
4. "New app" → elegís el repositorio que acabás de crear → en "Main
   file path" ponés `streamlit_app.py` → "Deploy".
5. Esperás un minuto y te da una URL (`algo.streamlit.app`) — esa es
   tu app, para siempre, gratis. Entrás desde el celu, la compu, y se
   la podés pasar a quien quieras.

**Sobre compartirla:** cualquiera con el link puede abrirla y cargar
sus propios datos — no hay usuarios ni login. Cada persona que la abre
tiene su propia sesión (ver "Cómo persisten los datos" abajo), así que
no ve la tuya. Si en algún momento te importa que sea privada, se le
puede agregar una contraseña simple — avisame y lo sumamos.

## Cómo persisten los datos

Streamlit Cloud no tiene una base de datos — cada vez que abrís la
app arranca desde `datos/movimientos.json` (lo que está en el
repositorio). Lo que cargues en una sesión (subir un archivo, agregar
a mano, guardar una foto de rendimiento) vive **mientras tengas la
pestaña abierta**, no se guarda solo entre visitas.

Para no perder lo que cargaste:
- Al pie de la pestaña **Movimientos**, hay un botón **"Descargar mi
  cartera"** — bajate ese archivo cuando termines de cargar algo.
- La próxima vez que abras la app, subilo con **"Restaurar una sesión
  guardada antes"** (mismo lugar) y seguís donde quedaste.
- Si querés que quede como el punto de partida "oficial" para
  siempre (no solo en tu sesión), mandame ese archivo por acá y lo
  subo al repositorio como nuevo `datos/movimientos.json` — exactamente
  el mismo flujo que usamos hasta ahora.

## Las tres pestañas

**Cartera** — posiciones agrupadas por broker. El campo **"Valor de
hoy"** siempre se carga en pesos (copiás el número directo de la app
de tu broker). El efectivo (USD/ARS líquidos) aparece como una tarjeta
más. Arriba, selector ARS/USD y la cotización que se está usando. Al
pie, un desplegable con el chequeo contable del historial (si "cierra"
o no, y por qué puede no cerrar del todo — ver más abajo).

**Evolución** — dos gráficos, con selector de fechas (desde/hasta):
1. *Capital invertido en el tiempo*: se calcula solo con el historial
   de movimientos, sin depender de precios de mercado.
2. *Rendimiento real*: arranca vacío. Cada "foto" que guardás (botón,
   con los valores ya cargados en Cartera, y opcionalmente el precio
   de SPY de ese día) suma un punto. Con dos fotos o más, aparece el
   gráfico comparando tu % de suba contra el de SPY.

**Movimientos** — subir un archivo (CSV o PDF, se reconocen los de
Cocos y Galicia solos) o cargar a mano; todo pasa por una vista previa
antes de confirmarse. Abajo, la lista completa filtrable, y los
botones de descargar/restaurar.

## Subir un banco/broker nuevo (Balanz, el que sea)

Hoy reconoce Cocos (CSV) y Galicia (PDF) automáticamente. Para uno
nuevo: subilo acá al chat, te armo `importadores/<broker>.py` (mismo
patrón que los otros dos — `detectar()` + `interpretar()`) y con eso
ya queda reconocible desde la app, sin tocar nada más.

## Límite conocido: el chequeo contable no cierra al 100%

`chequeo_identidad_ars()` convierte cada movimiento a pesos al tipo de
cambio de SU propia fecha, usando `datos/tipos_de_cambio.json` — una
serie armada con ~10 cotizaciones reales de tus propias operaciones
(no hay una fuente diaria todavía). La diferencia que queda (chica,
una fracción de porcentaje) es la aproximación de usar "la cotización
más cercana" en vez del dólar exacto de cada día. Se afina con una
fuente diaria real (`dolarapi.com`) — es un paso pendiente, no
bloquea nada de lo que ya funciona.

## Estructura

```
cartera-python/
├── streamlit_app.py             # LA APP — streamlit run streamlit_app.py
├── requirements.txt             # pip install -r requirements.txt
├── .streamlit/config.toml       # tema (colores)
├── modelo.py                    # Movimiento, Activo
├── motor.py                     # recalcular(), chequeo_identidad_ars()
├── importadores/
│   ├── cocos.py                 # CSV de Cocos Capital
│   ├── galicia.py               # PDF de resumen de Galicia
│   └── utils.py                 # fusionar() — dedup por huella al re-importar
├── datos/
│   ├── movimientos_cocos_raw.csv, movimientos_cocos_hist1.csv, hist2.csv  # tus exports, sin tocar
│   ├── galicia_raw.pdf              # tu resumen original, sin tocar
│   ├── movimientos.json             # 304 movimientos, la fuente "oficial"
│   ├── tipos_de_cambio.json         # cotizaciones reales
│   └── valores_conocidos.json       # valor real de hoy por posición — actualizalo a mano
├── tests/
│   └── test_motor.py            # python tests/test_motor.py
└── README.md
```

## Bitácora (decisiones y correcciones, para el detalle)

<details>
<summary>Ver el historial completo</summary>

**Motor**: `recalcular()` puro (FIFO por lotes, cajas por
broker/moneda, identidad contable). Test en `tests/test_motor.py`.

**Cocos** — reglas confirmadas, ver docstring de `cocos.py`: Compra/
Venta (+ variantes "Dolar Mep"), Recibo De Cobro/Orden De Pago
(+ "Usd"), Liquidacion Suscripcion/Rescate Fci (+ "Hb"), Dividendos/
Renta Y Amortizacion. Se ignoran: Nota De Credito Conversion
(+ "Cable"), Venta/Compra Registracion USD/ARS del bono T661O,
Concepto EXT migracion.

**Galicia** — solo se cargan operaciones de inversión (FIMA, bonos,
compra/venta de dólares, intereses); todo lo personal se descarta a
propósito. Cada compra de FIMA/bono se empareja con un depósito
implícito por el mismo monto.

**Bug corregido**: dos veces el bono AL30 se usó como vehículo para
comprar dólares con pesos (compra en ARS + venta en USD, mismo número
de operación, mismo día) — se lo tomaba como una posición real de
bono. Se detecta ese patrón y se trata como conversión de moneda.

**Ajustes de conciliación** (`fuente: ajuste-manual`): Cocos USD de
-262,94 a 0; Galicia USD de 1.287,26 a 580,00; FIMA Renta en Pesos de
450.750 a 485.000 (saldos reales confirmados).

**Versión HTML+JS abandonada** (16-17/09/2026): se portó todo a
JavaScript para que corriera sin instalar nada, verificado con Node
contra los mismos datos — pero se rompió por una restricción de los
navegadores con `file://` y scripts locales sueltos. Se migró a
Streamlit para tener una sola fuente de verdad en Python.

**Valores reales de hoy** (17/09/2026): la pantalla Cartera pasó de
calcular el valor a partir del historial (desactualizado) a usar
`valores_conocidos.json` + lo que cargues a mano en "Valor de hoy",
siempre en pesos.

</details>
