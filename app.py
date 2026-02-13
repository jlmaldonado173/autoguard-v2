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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(
    page_title="Itero", 
    layout="wide", 
    page_icon="🔄", 
    initial_sidebar_state="collapsed"
)

# Colores de marca (Semáforo solicitado)
CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4", "Otro": "#64748b"
}

# --- 2. DISEÑO CSS (OPTIMIZADO PARA MÓVIL) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    /* Barra Superior Personalizada */
    .top-bar {{
        background: #1e293b; color: white; padding: 12px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .main-content {{ margin-top: 80px; }}
    
    /* Botones Grandes */
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; transition: all 0.3s;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES CORE (PERSISTENCIA Y LOGO) ---

def show_logo(width=150, centered=True):
    """Muestra el logo 1000110802.png con manejo de errores"""
    if centered:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try: st.image("1000110802.png", use_container_width=True)
            except: st.markdown("### 🔄 ITERO")
    else:
        try: st.image("1000110802.png", width=width)
        except: st.markdown("### 🔄")

def session_persistence():
    """Script para mantener al usuario logueado en el navegador"""
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_v11_session');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

# --- 4. CONEXIÓN FIREBASE (REGLAS 1, 2, 3) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            # Asegúrate de tener FIREBASE_JSON en tus Secrets de Streamlit
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
                firebase_admin.initialize_app(cred)
            else:
                # Local fallback
                firebase_admin.initialize_app(credentials.Certificate("firebase_key.json"))
        except: return None
    return firestore.client()

db = init_db()
app_id = "itero-v11-main" # ID para esta nueva estructura limpia

def get_ref(collection_name):
    """Referencia estricta siguiendo la Regla 1"""
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(collection_name)

# --- 5. INICIALIZACIÓN DE ESTADO ---
session_persistence()

if 'user' not in st.session_state:
    if "session" in st.query_params:
        try: st.session_state.user = json.loads(st.query_params["session"])
        except: st.session_state.user = None
    else:
        st.session_state.user = None

if 'page' not in st.session_state:
    st.session_state.page = "🏠 Dashboard"

# --- 6. PANTALLA DE LOGIN (MODULAR) ---
def login_screen():
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Bienvenido a Itero</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:gray;'>Gestión de Mantenimiento de Flota</p>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Administrador"])
    
    with t1:
        with st.form("form_driver"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Tu Nombre")
            u_b = st.text_input("Número de Bus")
            if st.form_submit_button("INGRESAR"):
                user = {'role':'driver', 'fleet':f_id.upper(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                # Guardar sesión físicamente
                components.html(f"<script>window.localStorage.setItem('itero_v11_session', '{json.dumps(user)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(user)}');</script>", height=0)
                st.rerun()
                
    with t2:
        with st.form("form_owner"):
            f_o = st.text_input("Código de Flota")
            o_n = st.text_input("Nombre de Propietario")
            if st.form_submit_button("ACCESO ADMINISTRATIVO"):
                user = {'role':'owner', 'fleet':f_o.upper(), 'name':o_n}
                st.session_state.user = user
                components.html(f"<script>window.localStorage.setItem('itero_v11_session', '{json.dumps(user)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(user)}');</script>", height=0)
                st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
if st.session_state.user is None:
    login_screen()
else:
    u = st.session_state.user
    # Barra superior con marca
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    # --- NAVEGACIÓN (MENU LATERAL) ---
    with st.sidebar:
        show_logo(width=80, centered=False)
        st.title("Menú")
        
        # Opciones dinámicas según rol
        if u['role'] == 'owner':
            menu_options = ["🏠 Dashboard", "🛠️ Nuevo Reporte", "📋 Historial General", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales"]
        else:
            menu_options = ["🏠 Dashboard", "🛠️ Nuevo Reporte", "📋 Mis Arreglos"]
            
        selection = st.radio("Ir a:", menu_options, index=menu_options.index(st.session_state.page) if st.session_state.page in menu_options else 0)
        
        if selection != st.session_state.page:
            st.session_state.page = selection
            st.rerun()
            
        st.divider()
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_v11_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- ROUTER DE PÁGINAS (PARA IR AÑADIENDO POCO A POCO) ---
    if st.session_state.page == "🏠 Dashboard":
        st.header("📊 Estado de la Flota")
        st.info("Aquí pondremos los resúmenes financieros y deudas.")
        
    elif st.session_state.page == "🛠️ Nuevo Reporte":
        st.header("🛠️ Registrar Arreglo")
        st.info("Aquí pondremos el formulario con cámara y selección de mecánicos.")
        
    elif "Historial" in st.session_state.page or "Arreglos" in st.session_state.page:
        st.header("📋 Historial de Mantenimiento")
        st.info("Aquí pondremos las tarjetas de colores y evidencias.")

st.caption(f"Itero V11.0 | Base Estructurada | ID: {app_id}")
