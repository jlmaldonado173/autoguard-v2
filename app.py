import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time

# Intentar importar Plotly con seguridad para evitar el ModuleNotFoundError
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro v27.2 - Estable", layout="wide", page_icon="🛡️")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. MOTOR DE DATOS SEGURO (Evita el KeyError) ---
def load_safe_data(user_fleet, user_bus, user_role):
    query = DATA_REF.collection("logs").where("fleetId", "==", user_fleet)
    if user_role == 'driver':
        query = query.where("bus", "==", user_bus)
    
    docs = query.stream()
    logs = [l.to_dict() | {"id": l.id} for l in docs]
    
    if not logs:
        # Creamos un DataFrame vacío con las columnas necesarias para que no falle el sistema
        columns = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost']
        return pd.DataFrame(columns=columns)
    
    df = pd.DataFrame(logs)
    
    # Asegurar que las columnas críticas existan y sean numéricas
    cols_num = ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
    for c in cols_num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        else:
            df[c] = 0.0
            
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
    return df

# --- 3. LÓGICA DE INTERFAZ ---
if 'user' not in st.session_state:
    # (Simulamos login para el ejemplo, usa tu lógica de login aquí)
    st.session_state.user = {"role":"owner", "fleet":"SURLOJA", "name":"Admin", "bus":"01"}

u = st.session_state.user
df = load_safe_data(u['fleet'], u['bus'], u['role'])

st.sidebar.title("🛠️ Itaro Control")
menu = ["📋 Estado de Componentes", "⚙️ Registrar Arreglo", "📊 Análisis Técnico"]
choice = st.sidebar.radio("Navegación", menu)

if choice == "📋 Estado de Componentes":
    st.header("Estado Actual de los Componentes")
    
    if df.empty:
        st.info("👋 ¡Bienvenido! Aún no hay mantenimientos registrados. Ve a 'Registrar Arreglo' para empezar.")
    else:
        # Ahora el selectbox es seguro porque verificamos que df no esté vacío
        buses_disponibles = sorted(df['bus'].unique())
        bus_sel = st.selectbox("Seleccionar Bus", buses_disponibles)
        
        df_bus = df[df['bus'] == bus_sel].sort_values('date', ascending=False)
        latest_per_cat = df_bus.groupby('category').head(1)
        
        cols = st.columns(3)
        for i, (_, r) in enumerate(latest_per_cat.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.subheader(f"🔧 {r['category']}")
                    km_restante = r['km_next'] - r['km_current']
                    if km_restante <= 500:
                        st.error(f"¡CAMBIO URGENTE!\nFaltan {km_restante:,.0f} KM")
                    else:
                        st.success(f"Estado Óptimo\n{km_restante:,.0f} KM restantes")
                    st.caption(f"Último: {r['date'].strftime('%d/%m/%Y') if not pd.isnull(r['date']) else 'S/F'}")

elif choice == "📊 Análisis Técnico":
    st.header("Estudio de Durabilidad")
    if not PLOTLY_AVAILABLE:
        st.warning("⚠️ Gráficos desactivados. Instala 'plotly' en requirements.txt para verlos.")
        if not df.empty: st.dataframe(df)
    elif df.empty:
        st.info("Datos insuficientes para el análisis.")
    else:
        # Aquí iría el gráfico de Plotly
        st.write("Analítica de precisión lista.")
        # fig = px.bar(df, ...)

st.caption("Itaro v27.2 | Protección de datos y estabilidad activada")
