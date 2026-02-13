import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import time
import streamlit.components.v1 as components

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Itero", 
    layout="wide", 
    page_icon="🔄", 
    initial_sidebar_state="collapsed"
)

# --- 2. DISEÑO CSS PROFESIONAL ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background-color: #f8fafc; }
    
    /* Barra superior de estado */
    .top-bar {
        background: #1e293b; color: white; padding: 12px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .main-container { margin-top: 80px; }
    
    /* Estilo de botones táctiles */
    .stButton>button {
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; width: 100%; transition: all 0.3s;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE INFRAESTRUCTURA ---

def show_logo(width=150, centered=True):
    """Muestra el logo 1000110802.png"""
    if centered:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try: st.image("1000110802.png", use_container_width=True)
            except: st.markdown("<h1 style='text-align:center;'>🔄 ITERO</h1>", unsafe_allow_html=True)
    else:
        try: st.image("1000110802.png", width=width)
        except: st.markdown("### 🔄")

def session_persistence():
    """Mantiene la sesión activa en el navegador del usuario"""
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_v12_session');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

# --- 4. CONEXIÓN A BASE DE DATOS (FIREBASE) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app(credentials.Certificate("firebase_key.json"))
        except: return None
    return firestore.client()

db = init_db()
app_id = "itero-v12-main" # Nueva ruta limpia para evitar choques con versiones viejas

def get_ref(collection_name):
    """Obtiene la referencia a la base de datos (Regla 1)"""
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(collection_name)

# --- 5. GESTIÓN DE ESTADO ---
session_persistence()

if 'user' not in st.session_state:
    if "session" in st.query_params:
        try: st.session_state.user = json.loads(st.query_params["session"])
        except: st.session_state.user = None
    else:
        st.session_state.user = None

if 'page' not in st.session_state:
    st.session_state.page = "🏠 Inicio"

# --- 6. PANTALLA DE INGRESO (MENU INICIAL) ---
def login_screen():
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Bienvenido a Itero</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#64748b;'>Gestión Inteligente de Vehículos</p>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Propietario"])
    
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota (Ej: FLOTA01)")
            u_n = st.text_input("Nombre del Conductor")
            u_b = st.text_input("Número de Unidad / Bus")
            if st.form_submit_button("INGRESAR"):
                if f_id and u_n and u_b:
                    user_data = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                    st.session_state.user = user_data
                    # Guardar en memoria del navegador
                    components.html(f"<script>window.localStorage.setItem('itero_v12_session', '{json.dumps(user_data)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(user_data)}');</script>", height=0)
                    st.rerun()
                else: st.error("Por favor llena todos los campos.")

    with t2:
        with st.form("login_owner"):
            f_o = st.text_input("Código de Flota (Crea uno nuevo si no tienes)")
            o_n = st.text_input("Nombre del Propietario")
            if st.form_submit_button("ACCESO TOTAL"):
                if f_o and o_n:
                    user_data = {'role':'owner', 'fleet':f_o.upper().strip(), 'name':o_n}
                    st.session_state.user = user_data
                    components.html(f"<script>window.localStorage.setItem('itero_v12_session', '{json.dumps(user_data)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(user_data)}');</script>", height=0)
                    st.rerun()
                else: st.error("Por favor llena todos los campos.")

# --- 7. LOGICA DE LA APP (MENU Y NAVEGACIÓN) ---
if st.session_state.user is None:
    login_screen()
else:
    u = st.session_state.user
    # Barra de estado superior
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        show_logo(width=80, centered=False)
        st.title("Menu")
        
        # Opciones según el rol (Intercomunicación)
        if u['role'] == 'owner':
            options = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial General", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales"]
        else:
            options = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
            
        selection = st.radio("Ir a:", options, index=options.index(st.session_state.page) if st.session_state.page in options else 0)
        
        if selection != st.session_state.page:
            st.session_state.page = selection
            st.rerun()
            
        st.divider()
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_v12_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- ENRUTADOR DE PÁGINAS ---
    if st.session_state.page == "🏠 Inicio":
        st.header(f"📊 Dashboard - {u['role'].capitalize()}")
        st.info("Estructura base cargada. Aquí se mostrarán los indicadores de gastos y deudas.")
        
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Registro de Mantenimiento")
        st.info("Aquí insertaremos el formulario de reporte con cámara y categorías.")
        
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Carpeta de Registros")
        st.info("Aquí aparecerán las tarjetas con los arreglos y las fotos.")

st.caption(f"Itero V12.0 | Estructura de Intercomunicación | ID: {app_id}")
