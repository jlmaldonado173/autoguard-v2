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

# --- 1. CONFIGURACIÓN DE PÁGINA (ESTILO APP) ---
st.set_page_config(
    page_title="AutoGuard Elite V3.1", 
    layout="wide", 
    page_icon="🚌", 
    initial_sidebar_state="collapsed" # Escondemos el menú nativo para usar el nuestro
)

# Colores por sección
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. DISEÑO DE INTERFAZ PREMIUM (CSS) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    
    /* Fuente y fondo */
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f1f5f9; }}
    
    /* BARRA SUPERIOR ESTILO APP REAL */
    .top-app-bar {{
        background: #1e293b;
        color: white;
        padding: 15px 20px;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 1000;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }}
    
    .menu-toggle-btn {{
        background: #334155;
        color: white;
        border: none;
        padding: 8px 12px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 14px;
    }}

    /* Margen para que el contenido no quede debajo de la barra */
    .main-content {{ margin-top: 70px; }}

    /* Tarjetas de menú */
    .stButton>button {{
        border-radius: 16px;
        height: 4rem;
        font-weight: 700;
        background: white;
        color: #1e293b;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.2s;
    }}
    .stButton>button:active {{ transform: scale(0.96); }}
    
    /* Estilos de tarjetas de historial */
    .card {{ 
        background: white; 
        padding: 18px; 
        border-radius: 18px; 
        border: 1px solid #e2e8f0; 
        margin-bottom: 12px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.02); 
    }}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 11px; font-weight: bold; }}
    .pending {{ background: #fee2e2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background: #dcfce7; color: #16a34a; border: 1px solid #bbf7d0; }}

    /* Esconder flechas y elementos de Streamlit que molestan */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header {{ visibility: hidden; }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES TÉCNICAS ---
def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((600, 600))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v31_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v31_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v31_session'); window.parent.location.search = '';</script>", height=0)

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

# --- 5. LÓGICA DE NAVEGACIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

# Recuperar sesión de URL (Puente JS)
if st.session_state.user is None and "session" in st.query_params:
    try:
        st.session_state.user = json.loads(st.query_params["session"])
    except: pass

if st.session_state.user is None: session_persistence_js()

# --- 6. PANTALLA DE ACCESO ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#1e293b;'>🛡️ AutoGuard Pro</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("login_d"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("login_o"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Administrador")
            if st.form_submit_button("Acceso Total"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
else:
    u = st.session_state.user
    
    # BARRA SUPERIOR PERSONALIZADA (TU NUEVO MENÚ)
    st.markdown(f"""
        <div class='top-app-bar'>
            <span style='font-size:18px; font-weight:800;'>🛡️ AutoGuard</span>
            <span style='font-size:12px; opacity:0.8;'>Flota: {u['fleet']}</span>
        </div>
        <div class='main-content'></div>
    """, unsafe_allow_html=True)

    # SIDEBAR SIEMPRE DISPONIBLE (CON EL BOTÓN DE "TRES LÍNEAS" QUE BUSCABAS)
    with st.sidebar:
        st.markdown(f"### 👤 {u['name']}")
        st.divider()
        nav_options = ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Historial y Pagos", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "📦 Repuestos"] if u['role'] == 'owner' else ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Mis Reportes"]
        
        # Sincronizar selección
        try: idx = nav_options.index(st.session_state.page)
        except: idx = 0
            
        selection = st.radio("Navegación:", nav_options, index=idx)
        if selection != st.session_state.page:
            st.session_state.page = selection
            st.rerun()
            
        st.divider()
        if st.button("🚪 Cerrar Sesión", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- PÁGINAS ---

    if st.session_state.page == "🏠 Inicio":
        st.header("📈 Resumen de Flota")
        # Lectura segura de datos
        try:
            logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        except: logs = []
        
        if logs:
            df = pd.DataFrame(logs)
            
            # --- SOLUCIÓN AL ERROR KEYERROR (FOTO 3) ---
            # Forzamos que las columnas existan antes de hacer cálculos
            required_cols = {'paid': False, 'cost': 0.0, 'category': 'Otro', 'busNumber': 'S/N'}
            for col, val in required_cols.items():
                if col not in df.columns: df[col] = val

            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2 = st.columns(2)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            # Cálculo seguro de deudas
            deuda = df[df['paid'] == False]['cost'].sum()
            c2.metric("Pendiente", f"${deuda:,.2f}")
            
            st.subheader("Distribución por Sección")
            st.bar_chart(df.groupby('category')['cost'].sum())
        else:
            st.info("👋 Bienvenido, Jose. Aún no hay reportes. Registra el primero para ver estadísticas.")

        st.divider()
        st.subheader("Acceso Rápido")
        col1, col2 = st.columns(2)
        if col1.button("🛠️ REPORTAR\nDAÑO", use_container_width=True): 
            st.session_state.page = "🛠️ Reportar Daño"; st.rerun()
        if col2.button("📋 HISTORIAL\nY PAGOS", use_container_width=True): 
            st.session_state.page = "📋 Historial y Pagos" if u['role'] == 'owner' else "📋 Mis Reportes"; st.rerun()

    elif st.session_state.page == "🛠️ Reportar Daño":
        st.subheader(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        # Selectores inteligentes
        try: mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        except: mecs = []
        try: casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        except: casas = []
        
        with st.form("f_report"):
            cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló?")
            det = st.text_area("Detalle de la falla")
            cost = st.number_input("Costo Total $", min_value=0.0)
            
            st.info("📸 Asegúrate de dar permiso a la cámara en el candado del navegador.")
            foto = st.camera_input("Evidencia del Arreglo")
            
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            is_paid = st.checkbox("¿Ya está pagado?")
            
            if st.form_submit_button("🚀 ENVIAR REPORTE"):
                with st.spinner("Guardando..."):
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': is_paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Reporte guardado!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.subheader("📋 Historial y Pagos")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        try:
            logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        except: logs = []

        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        if logs:
            for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
                color = CAT_COLORS.get(l.get('category'), "#64748b")
                paid = l.get('paid', False)
                st.markdown(f"""
                <div class='card' style='border-left: 10px solid {color};'>
                    <div style='display:flex; justify-content:space-between'>
                        <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l.get('category')}</span>
                        <span class='status-badge {"paid" if paid else "pending"}'>{"PAGADO" if paid else "DEUDA"}</span>
                    </div>
                    <h4 style='margin:10px 0;'>{l.get('part_name', 'Arreglo')} - Bus {l.get('busNumber')}</h4>
                    <p style='font-size:14px; margin-bottom:5px;'><b>Costo:</b> ${l.get('cost', 0):,.2f} | <b>Mecánico:</b> {l.get('mechanic', 'Externo')}</p>
                </div>
                """, unsafe_allow_html=True)
                if l.get('image'):
                    with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)
                if not paid and u['role'] == 'owner':
                    if st.button(f"Saldar Pago ({l['id'][:4]})", key=l['id']):
                        get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()
        else: st.info("No hay historial aún.")

    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Gestión de Mecánicos")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        with st.form("f_mec_v31"):
            m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
            if st.form_submit_button("Guardar"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                st.success("Registrado"); st.rerun()
        
        try: mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        except: mecs = []
        for m in mecs: st.write(f"✅ **{m['name']}** - {m['specialty']} (📞 {m['phone']})")

st.caption(f"AutoGuard V3.1 | APK Interface Premium | ID: {app_id}")

