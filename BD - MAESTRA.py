import time
from datetime import datetime
import pandas as pd
import pymysql
import streamlit as st

# Configuración de la página con tema oscuro personalizado
st.set_page_config(
    page_title="Sincronizador Cello - BD Madre", page_icon="🔄", layout="wide"
)

st.markdown(
    """
    <style>
    .main { background-color: #050a10; color: #00d4ff; }
    .stSidebar { background-color: #0b1a29; }
    h1, h2, h3 { color: #00ff00; }
    .stMetric { background-color: #0b1a29; padding: 10px; border-radius: 5px; border: 1px solid #00d4ff; }
    </style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_connection(db_key):
    """Establece conexión persistente con MySQL usando los secretos de Streamlit"""
    cfg = st.secrets[db_key]
    return pymysql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        port=cfg.get("port", 3306),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def ejecutar_sincronizacion():
  """Extrae datos de bitacora_cello_datos, transforma el ID y los inserta en BD_MADRE"""
  try:
    conn_source = get_connection("source_db")
    conn_target = get_connection("target_db")

    # 1. Leer datos de la tabla origen
    query_read = (
        "SELECT ID, FECHA_HORA_LOGGER, DISPOSITIVO, VARIABLE, VALOR FROM"
        " bitacora_cello_datos"
    )
    df = pd.read_sql(query_read, conn_source)

    if df.empty:
      return 0, "No se encontraron registros en el origen."

    # 2. Transformar el campo ID (ej. 1 -> 1-A)
    df["ID"] = df["ID"].astype(str) + "-A"

    # 3. Insertar registros en la tabla destino (BD_MADRE)
    # Usamos INSERT IGNORE o manejo de duplicados para evitar errores si ya existen
    cursor = conn_target.cursor()
    query_insert = """
            INSERT INTO BD_MADRE (ID, FECHA_HORA_LOGGER, DISPOSITIVO, VARIABLE, VALOR) 
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            VALOR = VALUES(VALOR), 
            FECHA_HORA_LOGGER = VALUES(FECHA_HORA_LOGGER)
        """

    tuples = [tuple(x) for x in df.to_numpy()]
    cursor.executemany(query_insert, tuples)
    cursor.close()

    return len(df), f"Sincronización exitosa de {len(df)} registros."

  except Exception as e:
    return -1, str(e)


# Interfaz Gráfica en Streamlit
st.title("⚡ Sincronizador Automático: Cello ➔ BD_MADRE")
st.markdown("---")

# Barra lateral para controles y temporizador
st.sidebar.header("⚙️ Configuración de Ejecución")
intervalo_minutos = st.sidebar.selectbox(
    "Selecciona el intervalo del reloj ejecutor:",
    options=[1, 5, 10, 15, 30, 60],
    index=1,  # Por defecto 5 minutos
    format_func=lambda x: f"Cada {x} minuto(s)",
)

auto_run = st.sidebar.toggle("Activar Ejecución Automática", value=False)
btn_manual = st.sidebar.button("🚀 Sincronizar Ahora (Manual)")

col1, col2 = st.columns(2)
with col1:
  st.subheader("📊 Estado del Proceso")
  status_placeholder = st.empty()
with col2:
  st.subheader("🕒 Última Ejecución")
  time_placeholder = st.empty()

# Contenedor para mostrar registros procesados recientemente
st.markdown("---")
st.subheader("📋 Vista Previa de Datos Origen (`bitacora_cello_datos`)")
table_placeholder = st.empty()

try:
  conn_s = get_connection("source_db")
  df_preview = pd.read_sql(
      "SELECT * FROM bitacora_cello_datos ORDER BY FECHA_HORA_LOGGER DESC LIMIT"
      " 50",
      conn_s,
  )
  table_placeholder.dataframe(df_preview, use_container_width=True)
except Exception as ex:
  table_placeholder.error(
      f"No se pudo cargar la vista previa de la base de datos origen: {ex}"
  )

# Lógica de Ejecución Manual
if btn_manual:
  with st.spinner("Ejecutando transferencia y transformación de datos..."):
    count, msg = ejecutar_sincronizacion()
    if count >= 0:
      status_placeholder.success(f"✅ {msg}")
    else:
      status_placeholder.error(f"❌ Error: {msg}")
    time_placeholder.info(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Lógica del Reloj Ejecutor Automático
if auto_run:
  intervalo_segundos = intervalo_minutos * 60
  status_placeholder.info(
      f"🤖 Reloj automático activo. Sincronizando cada {intervalo_minutos}"
      " minuto(s)..."
  )

  # Bucle de ejecución periódica controlada por Streamlit
  while auto_run:
    count, msg = ejecutar_sincronizacion()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if count >= 0:
      status_placeholder.success(
          f"✅ [Auto {timestamp}] Sincronizados {count} registros correctamente."
      )
    else:
      status_placeholder.error(f"❌ [Auto {timestamp}] Error: {msg}")

    time_placeholder.info(timestamp)

    # Cuenta regresiva visual o espera en bloques para no congelar la app bruscamente
    tiempo_restante = intervalo_segundos
    progress_bar = st.sidebar.progress(0)

    for i in range(intervalo_segundos):
      time.sleep(1)
      # Actualizar barra de progreso lateral
      progreso = (i + 1) / intervalo_segundos
      progress_bar.progress(progreso)
      # Nota: Si el usuario desactiva el toggle, el script se re-ejecutará al interactuar,
      # pero para un ciclo continuo exacto se recomienda desplegar en Streamlit Community Cloud
      # o servidor local con soporte de bucles largos.
    progress_bar.empty()
