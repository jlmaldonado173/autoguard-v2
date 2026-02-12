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
st.set_page_config(page_title="AutoGuard Elite V2.9", layout="wide", page_icon="🚌", initial_sidebar_state="expanded")

CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. ESTILOS CSS ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .stButton>button {{
        border-radius: 15px;
        height: 3.5rem;
        font-weight: 700;
        text-transform: uppercase;
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
    try:
        img = Image.open(file)
        img.thumbnail((500, 500))
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=75)
        return base64.b64encode(buffered.getvalue()).decode()
    except: return None

def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v29_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v29_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v29_session'); window.parent.location.search = '';</script>", height=0)

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

if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass
if st.session_state.user is None: session_persistence_js()

# --- 6. VISTA: ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.9</h1>", unsafe_allow_html=True)
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

# --- 7. VISTA: APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='navbar'><span>👤 {u['name']}</span><span><b>{u['fleet']}</b></span></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("MENÚ")
        nav_options = ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Historial y Pagos", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "📦 Repuestos"] if u['role'] == 'owner' else ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Mis Reportes"]
        
        # Sincronizar selección
        current_idx = nav_options.index(st.session_state.page) if st.session_state.page in nav_options else 0
        selection = st.radio("Ir a:", nav_options, index=current_idx)
        if selection != st.session_state.page:
            st.session_state.page = selection
            st.rerun()
            
        st.divider()
        if st.button("🚪 CERRAR SESIÓN", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # PÁGINA: INICIO
    if st.session_state.page == "🏠 Inicio":
        st.header("📊 Resumen de Flota")
        logs_stream = get_ref("maintenance_logs").stream()
        logs = [l.to_dict() for l in logs_stream if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            df = pd.DataFrame(logs)
            
            # --- RED DE SEGURIDAD (FIX KEYERROR) ---
            for col in ['paid', 'cost', 'category', 'busNumber', 'part_name']:
                if col not in df.columns:
                    df[col] = False if col == 'paid' else (0.0 if col == 'cost' else "N/A")

            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2 = st.columns(2)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            # Filtro seguro para pendientes
            total_pendiente = df[df['paid'] == False]['cost'].sum()
            c2.metric("Pendiente", f"${total_pendiente:,.2f}")
            
            st.subheader("Gastos por Sección")
            if not df.empty:
                st.bar_chart(df.groupby('category')['cost'].sum())
        else:
            st.info("👋 Aún no hay reportes. Registra el primero para ver estadísticas.")

        st.divider()
        st.subheader("📱 ACCESO RÁPIDO")
        col1, col2 = st.columns(2)
        if col1.button("🛠️ REPORTAR\nDAÑO", use_container_width=True): st.session_state.page = "🛠️ Reportar Daño"; st.rerun()
        hist_label = "📋 VER\nHISTORIAL" if u['role'] == 'owner' else "📋 MIS\nREPORTES"
        if col2.button(hist_label, use_container_width=True): st.session_state.page = "📋 Historial y Pagos" if u['role'] == 'owner' else "📋 Mis Reportes"; st.rerun()

    # PÁGINA: REPORTAR
    elif st.session_state.page == "🛠️ Reportar Daño":
        st.subheader(f"🛠️ Nuevo Reporte - Unidad {u.get('bus', 'ADMIN')}")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        # Cargar selectores
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_v29"):
            cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló? (Ej: Rodillos)")
            det = st.text_area("Detalle")
            cost = st.number_input("Costo Total $", min_value=0.0)
            foto = st.camera_input("📸 Evidencia del arreglo")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            is_paid = st.checkbox("¿Ya está pagado?")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                with st.spinner("Guardando..."):
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': is_paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Reporte guardado!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    # PÁGINA: HISTORIAL
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.subheader("📋 Historial y Pagos")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        
        logs_stream = get_ref("maintenance_logs").stream()
        logs = [{"id": l.id, **l.to_dict()} for l in logs_stream if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        if logs:
            for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
                color = CAT_COLORS.get(l.get('category'), "#64748b")
                paid_status = l.get('paid', False)
                st.markdown(f"""
                <div class='card' style='border-left: 10px solid {color};'>
                    <div style='display:flex; justify-content:space-between'>
                        <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l.get('category')}</span>
                        <span class='status-badge {"paid" if paid_status else "pending"}'>{"PAGADO" if paid_status else "DEUDA"}</span>
                    </div>
                    <h4 style='margin:10px 0;'>{l.get('part_name', 'Arreglo')} - Bus {l.get('busNumber')}</h4>
                    <p style='font-size:14px; margin-bottom:5px;'><b>Costo:</b> ${l.get('cost', 0):,.2f} | <b>Mecánico:</b> {l.get('mechanic', 'Externo')}</p>
                </div>
                """, unsafe_allow_html=True)
                if l.get('image'):
                    with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)
                if not paid_status and u['role'] == 'owner':
                    if st.button(f"Marcar como Pagado ({l['id'][:4]})", key=l['id']):
                        get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()
        else: st.info("No hay registros aún.")

    # PÁGINA: MECÁNICOS
    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.subheader("👨‍🔧 Gestión de Mecánicos")
        if st.button("⬅️ VOLVER"): st.session_state.page = "🏠 Inicio"; st.rerun()
        with st.form("f_mec_v29"):
            m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
            if st.form_submit_button("Guardar"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                st.success("Mecánico registrado"); st.rerun()
        
        m_list = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in m_list: st.write(f"✅ **{m['name']}** - {m['specialty']}")

st.caption(f"AutoGuard V2.9 | Estabilidad Máxima | ID: {app_id}")

