import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro v27 - Precision Mechanic", layout="wide", page_icon="🔧")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. SESIÓN ---
if 'user' not in st.session_state:
    # (Mantenemos la lógica de login seguro previa...)
    st.session_state.user = {"role":"owner", "fleet":"SURLOJA", "name":"Admin", "bus":"01"} # Ejemplo

u = st.session_state.user

# --- 3. MOTOR DE ANÁLISIS TÉCNICO ---
def load_maint_data():
    query = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
    logs = [l.to_dict() | {"id": l.id} for l in query.stream()]
    df = pd.DataFrame(logs)
    if not df.empty:
        df['km_current'] = pd.to_numeric(df['km_current'], errors='coerce').fillna(0)
        df['km_next'] = pd.to_numeric(df['km_next'], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'])
        # Calcular durabilidad real (diferencia entre cambios de la misma categoría)
        df = df.sort_values(['bus', 'category', 'date'])
        df['durabilidad_real'] = df.groupby(['bus', 'category'])['km_current'].diff()
    return df

df_maint = load_maint_data()

# --- 4. INTERFAZ ENFOCADA EN MANTENIMIENTO ---
st.sidebar.title("🛠️ Itaro Mantenimiento")
menu = ["📋 Plan de Mantenimiento", "⚙️ Registrar Arreglo", "📊 Análisis de Repuestos"]
choice = st.sidebar.radio("Navegación Taller", menu)

if choice == "📋 Plan de Mantenimiento":
    st.header("Estado Actual de los Componentes")
    bus_sel = st.selectbox("Seleccionar Bus", df_maint['bus'].unique())
    
    # Filtramos por el último registro de cada categoría para ese bus
    latest_per_cat = df_maint[df_maint['bus'] == bus_sel].sort_values('date').groupby('category').last().reset_index()
    
    cols = st.columns(3)
    for i, (_, r) in enumerate(latest_per_cat.iterrows()):
        with cols[i % 3]:
            st.info(f"**{r['category']}**")
            km_faltantes = r['km_next'] - r['km_current']
            if km_faltantes <= 500:
                st.error(f"⚠️ CAMBIO URGENTE: {km_faltantes:,.0f} KM")
            else:
                st.success(f"Ok: {km_faltantes:,.0f} KM restantes")
            st.caption(f"Último cambio: {r['date'].strftime('%d/%m/%Y')}")

elif choice == "⚙️ Registrar Arreglo":
    st.subheader("Nuevo Ingreso a Taller")
    # (Formulario optimizado de las versiones anteriores...)
    # [Categoría, KM Actual, KM Próximo, Mecánico, Repuestos, Costos...]
    st.write("Registra aquí cada intervención para alimentar el historial de vida.")

elif choice == "📊 Análisis de Repuestos":
    st.header("Estudio de Durabilidad")
    st.write("Este gráfico muestra cuántos KM está durando cada repuesto antes de fallar.")
    
    if not df_maint.empty:
        # Filtrar solo registros que tienen un cálculo de durabilidad (el segundo cambio en adelante)
        df_dur = df_maint[df_maint['durabilidad_real'] > 0]
        if not df_dur.empty:
            fig = px.box(df_dur, x="category", y="durabilidad_real", points="all",
                         title="Kilómetros recorridos por componente entre cambios")
            st.plotly_chart(fig, use_container_width=True)
            st.write("💡 *Si una caja de barras es muy corta, significa que ese repuesto dura siempre lo mismo. Si es muy larga, la calidad varía mucho.*")
        else:
            st.info("Se necesitan al menos dos registros de la misma categoría para medir durabilidad.")
