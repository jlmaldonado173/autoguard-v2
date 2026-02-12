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

# --- 1. CONFIGURACIÓN Y COLORES (EL SEMÁFORO) ---
st.set_page_config(page_title="AutoGuard Elite V2.7", layout="wide", page_icon="🚌", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. ESTILOS CSS (BOTONES GRANDES PARA CELULAR) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    /* Diseño de tarjetas de menú */
    .menu-card {{
        background: white;
        padding: 20px;
        border-radius: 20px;
        border: 1px solid #e2e8f0;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 12px;
    }}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 12px; font-weight: bold; }}
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
        margin-bottom: 20px; 
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
        const stored = window.localStorage.getItem('autoguard_v27_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v27_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v27_session'); window.parent.location.search = '';</script>", height=0)

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

# --- 5. MANEJO DE PÁGINAS Y SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "Dashboard"

if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass
if st.session_state.user is None: session_persistence_js()

# --- 6. VISTA: ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.7</h1>", unsafe_allow_html=True)
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

# --- 7. VISTA: APLICACIÓN (BOTONES TÁCTILES) ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='navbar'><span>👤 {u['name']}</span><span><b>{u['fleet']}</b></span></div>", unsafe_allow_html=True)

    if st.session_state.page != "Dashboard":
        if st.button("⬅️ VOLVER AL INICIO", use_container_width=True):
            st.session_state.page = "Dashboard"; st.rerun()

    if st.session_state.page == "Dashboard":
        st.header("📈 Resumen de Operación")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            c1, c2 = st.columns(2)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente", f"${df[df.get('paid', False)==False]['cost'].sum():,.2f}")
        
        st.subheader("📱 MENÚ PRINCIPAL")
        if u['role'] == 'owner':
            c_a, c_b = st.columns(2)
            if c_a.button("🛠️ REPORTAR\nDAÑO", use_container_width=True): st.session_state.page = "Reportar"; st.rerun()
            if c_b.button("📋 VER\nHISTORIAL", use_container_width=True): st.session_state.page = "Historial"; st.rerun()
            c_c, c_d = st.columns(2)
            if c_c.button("👨‍🔧 VER\nMECÁNICOS", use_container_width=True): st.session_state.page = "Mecánicos"; st.rerun()
            if c_d.button("🏢 CASAS\nCOMERCIALES", use_container_width=True): st.session_state.page = "Casas"; st.rerun()
        else:
            if st.button("🛠️ REPORTAR NUEVO DAÑO", use_container_width=True): st.session_state.page = "Reportar"; st.rerun()
            if st.button("📋 VER MIS REPORTES", use_container_width=True): st.session_state.page = "Historial"; st.rerun()

        st.divider()
        if st.button("🚪 CERRAR SESIÓN", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    elif st.session_state.page == "Reportar":
        st.subheader(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        
        # Ayuda para la cámara (Solución a tu foto 4)
        with st.expander("❓ ¿La cámara no abre? Toca aquí"):
            st.info("Para activar la cámara: \n1. Toca los 3 puntos de Chrome (arriba a la derecha). \n2. Toca el icono de información 'i' o el candado. \n3. Busca 'Cámara' y dale a 'Permitir'.")

        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_v27"):
            cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
            p_name = st.text_input("Arreglo (Ej: Rodillos, Motor)")
            det = st.text_area("Detalle")
            cost = st.number_input("Costo $", min_value=0.0)
            foto = st.camera_input("📸 Toma foto del arreglo/factura")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            paid = st.checkbox("¿Ya está pagado?")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                with st.spinner("Guardando en la nube..."):
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Guardado!"); time.sleep(1); st.session_state.page = "Dashboard"; st.rerun()

    elif st.session_state.page == "Historial":
        st.subheader("📋 Historial Detallado")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color}; padding:15px; background:white; border-radius:15px; margin-bottom:10px; border:1px solid #eee;'>
                <div style='display:flex; justify-content:space-between'>
                    <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l['category']}</span>
                    <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "DEUDA"}</span>
                </div>
                <h4 style='margin:10px 0;'>{l.get('part_name')} - Bus {l.get('busNumber')}</h4>
                <p style='font-size:18px; font-weight:bold; color:#1e293b;'>${l['cost']:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
            if l.get('image'):
                with st.expander("🖼️ Ver Foto Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)
            if not l.get('paid') and u['role'] == 'owner':
                if st.button(f"Saldar Deuda {l['id'][:4]}", key=l['id']):
                    get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

st.caption(f"AutoGuard V2.7 | Gestión Total | ID: {app_id}")

