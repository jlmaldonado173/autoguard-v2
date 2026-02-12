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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard Elite V2.2", layout="wide", page_icon="🚌", initial_sidebar_state="expanded")

# --- MAPA DE COLORES POR SECCIÓN ---
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- ESTILOS CSS PREMIUM ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .card {{ background: white; padding: 20px; border-radius: 16px; border: 1px solid #e2e8f0; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    
    .section-tag {{ padding: 4px 12px; border-radius: 20px; color: white; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
    {" ".join([f".tag-{k} {{ background-color: {v}; }}" for k, v in CAT_COLORS.items()])}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 12px; font-weight: bold; }}
    .pending {{ background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    
    .navbar {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 12px 20px; border-radius: 12px; color: white; margin-bottom: 20px; }}
    
    .img-evidence {{ border-radius: 12px; border: 2px solid #e2e8f0; margin-top: 10px; }}
    </style>
    """, unsafe_allow_html=True)

# --- PROCESAMIENTO DE IMAGEN (OPTIMIZACIÓN) ---
def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        # Reducimos el tamaño para no saturar la base de datos y ahorrar datos
        img.thumbnail((500, 500))
        buffered = BytesIO()
        # Guardamos como JPEG comprimido
        img.save(buffered, format="JPEG", quality=70)
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        st.error(f"Error procesando imagen: {e}")
        return None

# --- PUENTE DE PERSISTENCIA ---
def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v22_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v22_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v22_session'); window.parent.location.search = '';</script>", height=0)

# --- FIREBASE ---
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
apiKey = "" # Gemini API

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- MANEJO DE SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass
if st.session_state.user is None: session_persistence_js()

# --- VISTA: ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.2</h1>", unsafe_allow_html=True)
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
            u_n_o = st.text_input("Nombre Admin")
            if st.form_submit_button("ACCESO TOTAL"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- VISTA: APP ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='navbar'><span>👤 {u['name']} | <b>{u['fleet']}</b></span><span>V2.2 VISION</span></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("AutoGuard")
        options = ["🏠 Dashboard", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "🛠️ Reportar Daño", "📋 Historial y Pagos", "🧠 Análisis IA"] if u['role'] == 'owner' else ["🏠 Inicio", "🛠️ Reportar Daño", "📋 Mis Reportes"]
        menu_opt = st.sidebar.radio("Navegación", options)
        st.divider()
        if st.sidebar.button("🚪 Cerrar Sesión", type="primary"):
            clear_session_js(); st.session_state.user = None; st.rerun()

    if "Dashboard" in menu_opt or "Inicio" in menu_opt:
        st.header("📈 Estado de Operación")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente", f"${df[df['paid']==False]['cost'].sum():,.2f}")
            c3.metric("Actividades", len(df))
            st.bar_chart(df.groupby('category')['cost'].sum())
        else: st.info("No hay datos aún.")

    elif menu_opt == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Directorio de Mecánicos")
        with st.form("f_mec"):
            m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
            if st.form_submit_button("Guardar"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                st.success("Registrado"); st.rerun()

    elif menu_opt == "🛠️ Reportar Daño":
        st.header(f"🛠️ Nuevo Reporte - Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep_vision"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
                p_name = st.text_input("Repuesto (Ej: Rodillos)")
                det = st.text_area("Detalle de falla")
            with col2:
                cost = st.number_input("Costo $", min_value=0.0)
                paid = st.checkbox("¿Ya pagado?")
                next_d = st.date_input("Próximo cambio", value=None)
            
            # --- CÁMARA PARA EVIDENCIA ---
            st.write("📸 **Evidencia del Arreglo/Factura**")
            foto_input = st.camera_input("Toma una foto para que el dueño la vea")
            
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            
            if st.form_submit_button("🚀 ENVIAR CON FOTO"):
                with st.spinner("Subiendo evidencia..."):
                    img_data = process_img(foto_input)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, # Guardamos el Base64
                        'next_change_date': str(next_d) if next_d else "",
                        'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Reporte y foto guardados!"); time.sleep(1); st.rerun()

    elif "Historial" in menu_opt or "Reportes" in menu_opt:
        st.header("📋 Historial con Evidencia")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            with st.container():
                st.markdown(f"""
                <div class='card' style='border-left: 10px solid {color}'>
                    <div style='display:flex; justify-content:space-between'>
                        <span class='section-tag tag-{l['category']}'>{l['category']}</span>
                        <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "PENDIENTE"}</span>
                    </div>
                    <h4 style='margin-top:10px'>{l.get('part_name')} - Bus {l.get('busNumber')}</h4>
                    <p><b>Detalle:</b> {l.get('description', 'Sin detalle')}</p>
                    <p><b>Costo:</b> ${l['cost']:,.2f} | <b>Mecánico:</b> {l.get('mechanic')}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # --- MOSTRAR FOTO SI EXISTE ---
                if l.get('image'):
                    with st.expander("🖼️ Ver Foto de Evidencia"):
                        st.image(base64.b64decode(l['image']), use_container_width=True, caption=f"Evidencia de {l.get('part_name')}")
                
                if not l.get('paid') and u['role'] == 'owner':
                    if st.button(f"Saldar Pago {l['id'][:4]}", key=l['id']):
                        get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

st.caption(f"AutoGuard Elite V2.2 | Vision Pro Active | ID: {app_id}")

