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

# --- 1. CONFIGURACIÓN Y COLORES ---
st.set_page_config(page_title="AutoGuard Elite V2.8", layout="wide", page_icon="🚌", initial_sidebar_state="expanded")

CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. ESTILOS CSS (DISEÑO MÓVIL Y ESCRITORIO) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    /* Estilo de Tarjetas y Botones */
    .stButton>button {{
        border-radius: 15px;
        height: 3.5rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s;
    }}
    
    .card {{ 
        background: white; 
        padding: 20px; 
        border-radius: 20px; 
        border: 1px solid #e2e8f0; 
        margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
    }}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 11px; font-weight: bold; }}
    .pending {{ background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    
    .navbar {{ 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        background: #1e293b; 
        padding: 15px 20px; 
        border-radius: 15px; 
        color: white; 
        margin-bottom: 25px; 
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO ---
def process_img(file):
    if file is None: return None
    img = Image.open(file)
    img.thumbnail((500, 500))
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=75)
    return base64.b64encode(buffered.getvalue()).decode()

def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v28_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v28_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v28_session'); window.parent.location.search = '';</script>", height=0)

# --- 4. FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app(credentials.Certificate("firebase_key.json"))
        except: return None
    return firestore.client()

db = init_firebase()
app_id = "auto-guard-v2-prod"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. MANEJO DE SESIÓN Y NAVEGACIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

# Recuperar sesión persistente
if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass
if st.session_state.user is None: session_persistence_js()

# --- 6. VISTA: ACCESO (LOGIN) ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.8</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administradores"])
    with t1:
        with st.form("d_login"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("o_login"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Administrador")
            if st.form_submit_button("PANEL TOTAL"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- 7. VISTA: APP PRINCIPAL (SISTEMA HÍBRIDO) ---
else:
    u = st.session_state.user
    
    # NAVBAR SUPERIOR
    st.markdown(f"<div class='navbar'><span>👤 {u['name']}</span><span><b>{u['fleet']}</b></span></div>", unsafe_allow_html=True)

    # --- SIDEBAR (EL MENÚ QUE VOLVIÓ) ---
    with st.sidebar:
        st.title("MENÚ")
        if u['role'] == 'owner':
            nav_options = ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Historial y Pagos", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "📦 Repuestos", "🧠 Auditoría IA"]
        else:
            nav_options = ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Mis Reportes"]
            
        # Actualizar página desde el sidebar
        selection = st.radio("Ir a:", nav_options, index=nav_options.index(st.session_state.page) if st.session_state.page in nav_options else 0)
        if selection != st.session_state.page:
            st.session_state.page = selection
            st.rerun()
            
        st.divider()
        if st.button("🚪 CERRAR SESIÓN", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- PÁGINA: INICIO (CON BOTONES TÁCTILES) ---
    if st.session_state.page == "🏠 Inicio":
        st.header("📊 Resumen de Flota")
        
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            c1, c2 = st.columns(2)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente", f"${df[df.get('paid', False)==False]['cost'].sum():,.2f}")
        
        st.divider()
        st.subheader("📱 ACCESO RÁPIDO")
        
        # Botones para navegación táctil (Por si el sidebar se esconde)
        if u['role'] == 'owner':
            col1, col2 = st.columns(2)
            if col1.button("🛠️ REPORTAR\nARREGLO", use_container_width=True): st.session_state.page = "🛠️ Reportar Daño"; st.rerun()
            if col2.button("📋 VER\nHISTORIAL", use_container_width=True): st.session_state.page = "📋 Historial y Pagos"; st.rerun()
            
            col3, col4 = st.columns(2)
            if col3.button("👨‍🔧 VER\nMECÁNICOS", use_container_width=True): st.session_state.page = "👨‍🔧 Mecánicos"; st.rerun()
            if col4.button("🏢 CASAS\nCOMERCIALES", use_container_width=True): st.session_state.page = "🏢 Casas Comerciales"; st.rerun()
        else:
            if st.button("🛠️ NUEVO REPORTE DE DAÑO", use_container_width=True): st.session_state.page = "🛠️ Reportar Daño"; st.rerun()
            if st.button("📋 VER MIS ARREGLOS", use_container_width=True): st.session_state.page = "📋 Mis Reportes"; st.rerun()

    # --- PÁGINA: REPORTAR DAÑO ---
    elif st.session_state.page == "🛠️ Reportar Daño":
        st.subheader(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        if st.button("⬅️ VOLVER AL INICIO"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_v28"):
            cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló? (Ej: Rodillos)")
            det = st.text_area("Detalle")
            cost = st.number_input("Costo Total $", min_value=0.0)
            foto = st.camera_input("📸 Toma foto del arreglo/factura")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            paid = st.checkbox("¿Ya está pagado?")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                img_data = process_img(foto)
                get_ref("maintenance_logs").add({
                    'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                    'category': cat, 'part_name': p_name, 'description': det,
                    'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                    'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("✅ ¡Guardado!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    # --- PÁGINA: HISTORIAL ---
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.subheader("📋 Historial y Control de Pagos")
        if st.button("⬅️ VOLVER AL INICIO"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color};'>
                <div style='display:flex; justify-content:space-between'>
                    <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l['category']}</span>
                    <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "DEUDA"}</span>
                </div>
                <h4 style='margin:10px 0;'>{l.get('part_name')} - Bus {l.get('busNumber')}</h4>
                <p><b>Mecánico:</b> {l.get('mechanic')} | <b>Costo:</b> ${l['cost']:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
            if l.get('image'):
                with st.expander("🖼️ Ver Foto"): st.image(base64.b64decode(l['image']), use_container_width=True)
            if not l.get('paid') and u['role'] == 'owner':
                if st.button(f"Saldar Deuda {l['id'][:4]}", key=l['id']):
                    get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

    # --- PÁGINA: MECÁNICOS ---
    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.subheader("👨‍🔧 Directorio de Mecánicos")
        if st.button("⬅️ VOLVER AL INICIO"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        with st.form("f_mec_v28"):
            m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
            if st.form_submit_button("Guardar Mecánico"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                st.success("Registrado"); st.rerun()
        
        m_list = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in m_list: st.write(f"✅ **{m['name']}** - 📞 {m['phone']} ({m['specialty']})")

st.caption(f"AutoGuard V2.8 | Navegación Híbrida | ID: {app_id}")

