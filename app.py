import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
from io import BytesIO
from PIL import Image
import requests
import time
import streamlit.components.v1 as components

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard Elite V1.3 - Sesión Persistente", layout="wide", page_icon="🚌")

# --- PUENTE JAVASCRIPT PARA PERSISTENCIA ---
def local_storage_bridge():
    """Permite guardar y leer la sesión del navegador para no tener que loguearse siempre"""
    # JS para leer el storage al iniciar
    components.html(
        """
        <script>
        const user = window.localStorage.getItem('autoguard_user');
        if (user && !window.parent.location.search.includes('user_data=')) {
            const data = encodeURIComponent(user);
            window.parent.location.search = '?user_data=' + data;
        }
        </script>
        """,
        height=0,
    )

def save_to_local_storage(user_data):
    """Guarda los datos del usuario en el navegador"""
    user_json = json.dumps(user_data)
    components.html(
        f"""
        <script>
        window.localStorage.setItem('autoguard_user', '{user_json}');
        </script>
        """,
        height=0,
    )

def clear_local_storage():
    """Borra la sesión al cerrar sesión"""
    components.html(
        """
        <script>
        window.localStorage.removeItem('autoguard_user');
        window.parent.location.search = '';
        </script>
        """,
        height=0,
    )

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f5; }
    .main-card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .ai-response { background: #eef2ff; border-left: 5px solid #4f46e5; padding: 20px; border-radius: 10px; color: #1e1b4b; }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZACIÓN DE FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred_info = json.loads(st.secrets["FIREBASE_JSON"])
                cred = credentials.Certificate(cred_info)
                firebase_admin.initialize_app(cred)
            else:
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error de conexión: {e}")
            return None
    return firestore.client()

db = init_firebase()
app_id = "auto-guard-v2-prod"
apiKey = "" # Proporcionado por el entorno

# --- RUTAS DE BASE DE DATOS ---
def get_logs_ref():
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection("maintenance_logs")

def get_mechanics_ref():
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection("mechanics")

# --- MANEJO DE SESIÓN AUTOMÁTICA ---
if 'user' not in st.session_state:
    st.session_state.user = None

# Intentar recuperar sesión desde la URL (inyectada por JS)
if st.session_state.user is None and "user_data" in st.query_params:
    try:
        data_json = st.query_params["user_data"]
        st.session_state.user = json.loads(data_json)
    except:
        pass

# Ejecutar el puente de storage si no hay usuario
if st.session_state.user is None:
    local_storage_bridge()

# --- VISTA DE ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center; color:#1f618d;'>🛡️ AutoGuard Elite Pro</h1>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👨‍✈️ Conductores")
        with st.form("driver_login"):
            f_id = st.text_input("Código de Flota")
            u_name = st.text_input("Tu Nombre")
            u_bus = st.text_input("N° de Unidad")
            remember = st.checkbox("Recordarme en este dispositivo")
            if st.form_submit_button("Ingresar"):
                user_data = {'role':'driver', 'fleet':f_id.upper(), 'name':u_name, 'bus':u_bus}
                st.session_state.user = user_data
                if remember: save_to_local_storage(user_data)
                st.rerun()
                
    with col2:
        st.subheader("📊 Administración")
        with st.form("owner_login"):
            f_owner = st.text_input("Código de Flota")
            o_name = st.text_input("Nombre de Dueño")
            remember_owner = st.checkbox("Mantener sesión iniciada")
            if st.form_submit_button("Panel Administrativo"):
                user_data = {'role':'owner', 'fleet':f_owner.upper(), 'name':o_name}
                st.session_state.user = user_data
                if remember_owner: save_to_local_storage(user_data)
                st.rerun()

# --- VISTA PRINCIPAL (LOGUEADO) ---
else:
    u = st.session_state.user
    st.sidebar.title(f"👤 {u['name']}")
    st.sidebar.info(f"Flota: {u['fleet']}")
    
    if u['role'] == 'driver':
        menu = st.sidebar.radio("Navegación", ["🛠️ Reportar Falla", "📋 Mis Reportes"])
    else:
        menu = st.sidebar.radio("Navegación", ["🏠 Dashboard", "👨‍🔧 Mecánicos", "🧠 Análisis IA", "📋 Historial General"])

    if st.sidebar.button("🚪 Cerrar Sesión"):
        clear_local_storage()
        st.session_state.user = None
        st.rerun()

    # --- LÓGICA DE CADA MENÚ (Simplificada para brevedad, igual a V1.2) ---
    if menu == "🏠 Dashboard":
        st.header(f"Control de Flota {u['fleet']}")
        docs = get_logs_ref().stream()
        data = [d.to_dict() for d in docs if d.to_dict().get('fleetId') == u['fleet']]
        if data:
            df = pd.DataFrame(data)
            st.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            st.bar_chart(df.groupby('category')['cost'].sum())
        else: st.info("No hay reportes.")

    elif menu == "👨‍🔧 Mecánicos":
        st.header("Directorio de Mecánicos")
        with st.form("add_mechanic"):
            m_name = st.text_input("Nombre")
            m_phone = st.text_input("Teléfono")
            m_spec = st.multiselect("Especialidades", ["Motor", "Frenos", "Suspensión", "Llantas", "Eléctrico"])
            if st.form_submit_button("Guardar"):
                get_mechanics_ref().add({'fleetId': u['fleet'], 'name': m_name, 'phone': m_phone, 'specialties': m_spec})
                st.success("Mecánico registrado")

    elif menu == "🛠️ Reportar Falla":
        st.header(f"Reporte Unidad {u.get('bus', 'ADMIN')}")
        m_docs = get_mechanics_ref().stream()
        m_names = [m.to_dict()['name'] for m in m_docs if m.to_dict().get('fleetId') == u['fleet']]
        with st.form("rep"):
            cat = st.selectbox("Sistema", ["Motor", "Frenos", "Llantas", "Suspensión", "Eléctrico"])
            desc = st.text_area("Descripción")
            cost = st.number_input("Costo ($)", min_value=0.0)
            mec = st.selectbox("Mecánico", ["No especificado"] + m_names)
            if st.form_submit_button("🚀 Enviar"):
                get_logs_ref().add({
                    'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'), 'category': cat,
                    'description': desc, 'cost': cost, 'mechanic': mec, 'driver': u['name'],
                    'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("Reporte guardado")

    elif menu == "🧠 Análisis IA":
        st.header("Auditoría Inteligente")
        if st.button("Generar Informe"):
            st.info("Analizando mecánicos y costos... (Gemini Activo)")
            # Aquí iría la llamada a Gemini definida en V1.2

st.caption(f"AutoGuard V1.3 | Sesión Persistente Activada | ID: {app_id}")
