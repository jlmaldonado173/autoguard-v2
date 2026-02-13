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

# Semáforo de Colores (Pedido por Jose)
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Carrocería": "#ec4899",   # Rosado
    "Otro": "#64748b"          # Gris
}

# --- 2. DISEÑO CSS APK (COLORES Y TARJETAS) ---
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
        const stored = window.localStorage.getItem('itero_v14_session');
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
app_id = "itero-v14-main"

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

# --- 6. INTERFAZ DE INGRESO ---
if st.session_state.user is None:
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Centro de Control</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Dueño"])
    with t1:
        with st.form("l_d"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                if f_id:
                    user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                    st.session_state.user = user
                    js = json.dumps(user)
                    components.html(f"<script>window.localStorage.setItem('itero_v14_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                    st.rerun()
                else: st.error("Falta código de flota")
    with t2:
        with st.form("l_o"):
            f_o = st.text_input("Código de Flota")
            o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("Acceso Total"):
                if f_o:
                    user = {'role':'owner', 'fleet':f_o.upper().strip(), 'name':o_n}
                    st.session_state.user = user
                    js = json.dumps(user)
                    components.html(f"<script>window.localStorage.setItem('itero_v14_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                    st.rerun()
                else: st.error("Falta código de flota")

# --- 7. APP PRINCIPAL (INTERCOMUNICACIÓN) ---
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
            components.html("<script>window.localStorage.removeItem('itero_v14_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- PÁGINA: INICIO (DASHBOARD) ---
    if st.session_state.page == "🏠 Inicio":
        st.header(f"📊 Dashboard Flota {u['fleet']}")
        
        # Intercomunicación: Traer datos de la flota
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df.get('cost', 0) - df.get('abono', 0)
            
            c1, c2 = st.columns(2)
            c1.metric("Inversión Flota", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente de Pago", f"${df['deuda'].sum():,.2f}", delta_color="inverse")
            
            st.subheader("Estado por Unidades")
            buses = sorted(df['busNumber'].unique())
            cols = st.columns(2)
            for i, b in enumerate(buses):
                b_df = df[df['busNumber'] == b]
                with cols[i % 2]:
                    st.markdown(f"<div class='bus-card'><h4>BUS {b}</h4><p>Total: ${b_df['cost'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else:
            st.info("Aún no hay datos reportados en esta flota.")

    # --- PÁGINA: REPORTAR ARREGLO ---
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Nuevo Registro")
        with st.form("f_reporte", clear_on_submit=True):
            bus_num = u.get('bus', "")
            if u['role'] == 'owner': bus_num = st.text_input("Número de Bus")
            
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            trabajo = st.text_input("¿Qué se arregló? (Ej: Rodillos)")
            falla = st.text_input("Falla encontrada (Ej: Sin frenos)")
            
            c1, c2 = st.columns(2)
            costo = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            
            foto = st.camera_input("📸 Evidencia")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if costo > 0 and bus_num != "":
                    # Guardado con intercomunicación
                    get_ref("logs").add({
                        'fleetId': u['fleet'],
                        'busNumber': bus_num,
                        'category': cat,
                        'part': trabajo,
                        'fault': falla,
                        'cost': costo,
                        'abono': abono,
                        'date': datetime.now().strftime("%d/%m/%Y"),
                        'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Guardado!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()
                else: st.error("Completa los datos")

    # --- PÁGINA: HISTORIAL ---
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Carpeta de Mantenimiento")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l['busNumber'] == u['bus']]
        
        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            st.markdown(f"""
            <div class='bus-card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span style='background:{color}; color:white; padding:2px 10px; border-radius:10px; font-size:10px; font-weight:bold;'>{l.get('category')}</span>
                    <span style='color:gray; font-size:12px;'>{l.get('date')}</span>
                </div>
                <h4 style='margin:10px 0;'>Bus {l.get('busNumber')} - {l.get('part')}</h4>
                <p style='font-size:13px; color:#1e293b'><b>Falla:</b> {l.get('fault', 'S/D')}</p>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span style='font-weight:800'>${l.get('cost', 0):,.2f}</span>
                    <span style='color:{"#16a34a" if l["cost"]==l["abono"] else "#ef4444"}; font-weight:bold; font-size:12px;'>
                        {"✅ PAGADO" if l["cost"]==l["abono"] else f"🚨 DEBE: ${l['cost']-l['abono']:,.2f}"}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.caption(f"Itero V14.0 | Intercomunicación Activa | ID: {app_id}")
