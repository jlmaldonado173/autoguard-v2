import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import time
import streamlit.components.v1 as components
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itero Pro", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4",
    "Carrocería": "#ec4899", "Otro": "#64748b"
}

# --- 2. DISEÑO CSS APK ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    .top-bar {{
        background: #1e293b; color: white; padding: 12px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}
    .main-content {{ margin-top: 85px; }}
    .bus-card {{
        background: white; padding: 20px; border-radius: 24px;
        border: 1px solid #e2e8f0; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; width: 100%; transition: all 0.3s;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO ---
def show_logo(width=150, centered=True):
    if centered:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try: st.image("1000110802.png", use_container_width=True)
            except: st.markdown("<h1 style='text-align:center;'>🔄 ITERO</h1>", unsafe_allow_html=True)
    else:
        try: st.image("1000110802.png", width=width)
        except: st.markdown("### 🔄")

def session_persistence():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_v15_session');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            const currentUrl = window.parent.location.origin + window.parent.location.pathname;
            window.parent.location.href = currentUrl + '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

# --- 4. FIREBASE (REGLAS 1, 2, 3) ---
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
app_id = "itero-v15-secure"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. GESTIÓN DE SESIÓN ---
session_persistence()

if 'user' not in st.session_state:
    if "session" in st.query_params:
        try: st.session_state.user = json.loads(st.query_params["session"])
        except: st.session_state.user = None
    else: st.session_state.user = None

if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

# --- 6. INTERFAZ DE INGRESO CON VALIDACIÓN ---
if st.session_state.user is None:
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Seguridad de Flota</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Dueño"])
    
    with t1:
        with st.form("l_driver_secure"):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_n = st.text_input("Tu Nombre")
            u_b = st.text_input("N° de Bus")
            if st.form_submit_button("Ingresar"):
                if f_id:
                    # VALIDACIÓN: ¿Existe la flota?
                    fleet_ref = get_ref("fleets").document(f_id).get()
                    if fleet_ref.exists:
                        user = {'role':'driver', 'fleet':f_id, 'name':u_n, 'bus':u_b}
                        st.session_state.user = user
                        js = json.dumps(user)
                        components.html(f"<script>window.localStorage.setItem('itero_v15_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()
                    else:
                        st.error("❌ El Código de Flota no existe. Pídele el código correcto a tu jefe.")
                else: st.error("Ingresa el código")

    with t2:
        with st.form("l_owner_secure"):
            f_o = st.text_input("Código de Flota (Crea uno o usa el tuyo)").upper().strip()
            o_n = st.text_input("Nombre del Dueño")
            if st.form_submit_button("Gestionar Flota"):
                if f_o and o_n:
                    # VALIDACIÓN DE DUEÑO
                    fleet_ref = get_ref("fleets").document(f_o).get()
                    if fleet_ref.exists:
                        data = fleet_ref.to_dict()
                        if data.get('owner_name') == o_n:
                            # Login exitoso
                            user = {'role':'owner', 'fleet':f_o, 'name':o_n}
                            st.session_state.user = user
                            js = json.dumps(user)
                            components.html(f"<script>window.localStorage.setItem('itero_v15_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                            st.rerun()
                        else:
                            st.error(f"⚠️ El código {f_o} ya pertenece a otro dueño. Usa otro código o verifica tu nombre.")
                    else:
                        # REGISTRO DE NUEVA FLOTA
                        get_ref("fleets").document(f_o).set({
                            'owner_name': o_n,
                            'createdAt': datetime.now()
                        })
                        user = {'role':'owner', 'fleet':f_o, 'name':o_n}
                        st.session_state.user = user
                        js = json.dumps(user)
                        components.html(f"<script>window.localStorage.setItem('itero_v15_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.success(f"✅ Flota {f_o} registrada a nombre de {o_n}")
                        time.sleep(1); st.rerun()
                else: st.error("Completa todos los campos")

# --- 7. APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        show_logo(80, False)
        st.title("Menu")
        opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial General", "👨‍🔧 Mecánicos"]
        if u['role'] == 'driver': opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Ir a:", opts, index=opts.index(st.session_state.page) if st.session_state.page in opts else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
            
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_v15_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- CONTENIDO ---
    if st.session_state.page == "🏠 Inicio":
        st.header(f"📊 Dashboard {u['fleet']}")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            st.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
        else: st.info("Aún no hay reportes.")

    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Nuevo Reporte")
        with st.form("f_rep", clear_on_submit=True):
            bus_num = u.get('bus', "")
            if u['role'] == 'owner': bus_num = st.text_input("Bus")
            cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
            trabajo = st.text_input("¿Qué se arregló?")
            costo = st.number_input("Costo $", min_value=0.0)
            abono = st.number_input("Abono $", min_value=0.0)
            if st.form_submit_button("Guardar"):
                get_ref("logs").add({
                    'fleetId': u['fleet'], 'busNumber': bus_num, 'category': cat,
                    'part': trabajo, 'cost': costo, 'abono': abono,
                    'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("✅ Guardado"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        for l in logs:
            st.write(f"Bus {l['busNumber']} - {l['part']} - ${l['cost']}")

st.caption(f"Itero V15.0 | Acceso Validado | ID: {app_id}")
