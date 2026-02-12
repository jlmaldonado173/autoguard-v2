import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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
st.set_page_config(page_title="AutoGuard Elite V2.6", layout="wide", page_icon="🚌", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. ESTILOS CSS PARA MÓVILES (BOTONES GRANDES) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    /* Botones de Menú Principal */
    .menu-card {{
        background: white;
        padding: 20px;
        border-radius: 20px;
        border: 1px solid #e2e8f0;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        margin-bottom: 10px;
        transition: all 0.2s;
    }}
    .menu-card:active {{ transform: scale(0.95); background-color: #f1f5f9; }}
    
    .card {{ background: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; margin-bottom: 15px; }}
    
    .section-tag {{ padding: 4px 12px; border-radius: 20px; color: white; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
    {" ".join([f".tag-{k} {{ background-color: {v}; }}" for k, v in CAT_COLORS.items()])}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 12px; font-weight: bold; }}
    .pending {{ background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    
    .navbar {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 15px 20px; border-radius: 15px; color: white; margin-bottom: 20px; }}
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
        const stored = window.localStorage.getItem('autoguard_v26_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v26_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v26_session'); window.parent.location.search = '';</script>", height=0)

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
if 'page' not in st.session_state: st.session_state.page = "Dashboard"

if st.session_state.user is None and "session" in st.query_params:
    try:
        st.session_state.user = json.loads(st.query_params["session"])
    except: pass

if st.session_state.user is None: session_persistence_js()

# --- 6. VISTA: ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.6</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administradores"])
    with t1:
        with st.form("d_login"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Tu Nombre")
            u_b = st.text_input("N° de Bus")
            if st.form_submit_button("Ingresar"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("o_login"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Nombre Administrador")
            if st.form_submit_button("Acceso Total"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- 7. VISTA: APLICACIÓN (TOUCH NAVIGATION) ---
else:
    u = st.session_state.user
    
    # NAVBAR SUPERIOR
    st.markdown(f"""
        <div class='navbar'>
            <span>👤 {u['name']}</span>
            <span><b>{u['fleet']}</b></span>
        </div>
    """, unsafe_allow_html=True)

    # BARRA DE NAVEGACIÓN PRINCIPAL (Si el sidebar no se ve)
    if st.session_state.page != "Dashboard":
        if st.button("⬅️ VOLVER AL MENÚ PRINCIPAL", use_container_width=True):
            st.session_state.page = "Dashboard"
            st.rerun()

    # --- CONTENIDO SEGÚN LA PÁGINA ---
    
    # PÁGINA 1: DASHBOARD / MENÚ DE BOTONES
    if st.session_state.page == "Dashboard":
        st.header("📈 Resumen de Operación")
        
        # Estadísticas Rápidas
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            c1, c2 = st.columns(2)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Reportes", len(df))
        
        st.divider()
        st.subheader("📱 MENÚ DE ACCESO RÁPIDO")
        
        # Grid de botones según el rol
        if u['role'] == 'owner':
            col_a, col_b = st.columns(2)
            if col_a.button("🛠️ REPORTAR\nDAÑO", use_container_width=True): st.session_state.page = "Reportar"; st.rerun()
            if col_b.button("📋 VER\nHISTORIAL", use_container_width=True): st.session_state.page = "Historial"; st.rerun()
            
            col_c, col_d = st.columns(2)
            if col_c.button("👨‍🔧 VER\nMECÁNICOS", use_container_width=True): st.session_state.page = "Mecánicos"; st.rerun()
            if col_d.button("🏢 CASAS\nCOMERCIALES", use_container_width=True): st.session_state.page = "Casas"; st.rerun()
            
            col_e, col_f = st.columns(2)
            if col_e.button("📦 VER\nREPUESTOS", use_container_width=True): st.session_state.page = "Repuestos"; st.rerun()
            if col_f.button("🧠 AUDITORÍA\nIA", use_container_width=True): st.session_state.page = "IA"; st.rerun()
        else:
            if st.button("🛠️ REPORTAR NUEVO DAÑO", use_container_width=True): st.session_state.page = "Reportar"; st.rerun()
            if st.button("📋 VER MIS REPORTES", use_container_width=True): st.session_state.page = "Historial"; st.rerun()

        st.divider()
        if st.button("🚪 CERRAR SESIÓN", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # PÁGINA 2: REPORTAR
    elif st.session_state.page == "Reportar":
        st.subheader(f"🛠️ Nuevo Reporte - Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep_v26"):
            cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló?")
            det = st.text_area("Detalle de la falla")
            cost = st.number_input("Costo Total $", min_value=0.0)
            foto = st.camera_input("📸 Toma foto del arreglo/factura")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            paid = st.checkbox("¿Ya está pagado?")
            
            if st.form_submit_button("🚀 ENVIAR REPORTE"):
                with st.spinner("Guardando..."):
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Guardado!"); time.sleep(1); st.session_state.page = "Dashboard"; st.rerun()

    # PÁGINA 3: HISTORIAL
    elif st.session_state.page == "Historial":
        st.subheader("📋 Historial y Pagos")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span class='section-tag tag-{l['category']}'>{l['category']}</span>
                    <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "PENDIENTE"}</span>
                </div>
                <h4 style='margin-top:10px'>{l.get('part_name')} - Bus {l.get('busNumber')}</h4>
                <p><b>Costo:</b> ${l['cost']:,.2f} | <b>Mecánico:</b> {l.get('mechanic')}</p>
            </div>
            """, unsafe_allow_html=True)
            if l.get('image'):
                with st.expander("🖼️ Ver Foto"): st.image(base64.b64decode(l['image']), use_container_width=True)
            if not l.get('paid') and u['role'] == 'owner':
                if st.button(f"Saldar Pago {l['id'][:4]}", key=l['id']):
                    get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

    # PÁGINA 4: MECÁNICOS
    elif st.session_state.page == "Mecánicos":
        st.subheader("👨‍🔧 Gestión de Mecánicos")
        with st.form("f_mec_v26"):
            m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
            if st.form_submit_button("Guardar"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                st.rerun()
        
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in mecs: st.write(f"✅ **{m['name']}** - {m['specialty']}")

st.caption(f"AutoGuard V2.6 | Navegación Táctica | ID: {app_id}")

