import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Itaro SaaS v44", layout="wide", page_icon="🏢")

try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")
MASTER_KEY = "ADMIN123" # Tu clave de dueño de la App

# --- 2. PERSISTENCIA Y SEGURIDAD SaaS ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b")}
        st.rerun()

# --- 3. PANTALLA DE ACCESO MULTINIVEL ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Gestión Integral")
    t1, t2, t3 = st.tabs(["👤 Acceso Personal", "📝 Nueva Empresa", "👑 Super Admin"])

    with t1: # LOGIN CLIENTES
        f_in = st.text_input("Código de Flota").upper().strip()
        u_in = st.text_input("Usuario").upper().strip()
        u_role = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
        if st.button("INGRESAR"):
            if f_in and u_in:
                fleet = FLEETS_REF.document(f_in).get()
                if fleet.exists:
                    f_data = fleet.to_dict()
                    if f_data.get('status') == 'suspended':
                        st.error("🚫 SERVICIO SUSPENDIDO. CONTACTE AL PROVEEDOR.")
                    else:
                        auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_name if 'u_name' in locals() else u_in).get()
                        if "Adm" in u_role or auth.exists:
                            u_data = {'role':'owner' if "Adm" in u_role else 'driver', 'fleet':f_in, 'name':u_in, 'bus':"0"}
                            st.session_state.user = u_data
                            st.query_params.update({"f":f_in, "u":u_in, "r":u_data['role']})
                            st.rerun()
                        else: st.error("No autorizado.")
                else: st.error("Flota inexistente.")

    with t2: # REGISTRO CLIENTES
        n_f = st.text_input("ID Empresa").upper().strip()
        n_o = st.text_input("Dueño").upper().strip()
        if st.button("REGISTRAR"):
            if n_f and not FLEETS_REF.document(n_f).get().exists:
                FLEETS_REF.document(n_f).set({"owner": n_o, "status": "active", "date": datetime.now()})
                st.success("Empresa creada.")

    with t3: # SUPER ADMIN (TÚ)
        key = st.text_input("Master Key", type="password")
        if key == MASTER_KEY:
            st.subheader("Control Global de Suscripciones")
            for f in FLEETS_REF.stream():
                d = f.to_dict()
                c1, c2, c3 = st.columns(3)
                c1.write(f"🏢 {f.id}")
                st_now = d.get('status','active')
                c2.write(f"Estado: {st_now}")
                if c3.button("CONMUTAR", key=f.id):
                    FLEETS_REF.document(f.id).update({"status": "suspended" if st_now == 'active' else 'active'})
                    st.rerun()

else:
    # --- 4. SISTEMA OPERATIVO ---
    u = st.session_state.user
    
    def load_data():
        p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        
        q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
        
        df = pd.DataFrame(logs)
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'mec_name', 'com_name']
        if df.empty: df = pd.DataFrame(columns=cols)
        for c in cols: 
            if c not in df.columns: df[c] = 0
        for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df

    providers, df = load_data()

    st.sidebar.title(f"🚀 {u['fleet']}")
    menu = ["🏠 Dashboard Inteligente", "🛠️ Taller", "📈 Actualizar KM", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal")
    choice = st.sidebar.radio("Ir a:", menu)

    # --- MÓDULO INTELIGENTE (ALERTAS) ---
    if choice == "🏠 Dashboard Inteligente":
        st.header("Notificaciones de Mantenimiento")
        bus_list = df['bus'].unique() if u['role'] == 'owner' else [u['bus']]
        for b in bus_list:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                maint = b_df[b_df['km_next'] > 0]
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"### Unidad {b}")
                    c2.metric("KM Actual", f"{latest['km_current']:,.0f}")
                    
                    if not maint.empty:
                        last_m = maint.iloc[0]
                        restante = last_m['km_next'] - latest['km_current']
                        if restante <= 100: c3.error(f"🚨 URGENTE: {last_m['category']} ({restante}km)")
                        elif restante <= 500: c3.warning(f"🟡 AVISO: {last_m['category']} ({restante}km)")
                        else: c3.success(f"🟢 OK: {last_m['category']}")
                    
                    if (datetime.now() - latest['date']).days >= 3:
                        st.warning(f"⚠️ Unidad {b} requiere actualizar KM (más de 3 días sin reporte).")

    # --- ACTUALIZAR KM (SOLO KM) ---
    elif choice == "📈 Actualizar KM":
        st.subheader("Reporte Diario de Kilometraje")
        with st.form("km_daily"):
            bus_f = st.text_input("N° Unidad", value=u['bus'])
            km_f = st.number_input("Kilometraje Actual", min_value=0)
            if st.form_submit_button("Sincronizar"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": bus_f, "date": datetime.now().isoformat(),
                    "category": "Update KM", "km_current": km_f, "km_next": 0
                })
                st.success("Sincronizado"); time.sleep(1); st.rerun()

    # --- TALLER (REGISTRA PRÓXIMO CAMBIO) ---
    elif choice == "🛠️ Taller":
        st.subheader("Registro de Mantenimiento Programado")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        with st.form("taller_v44"):
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Componente", ["Aceite", "Frenos", "Llantas", "Caja", "Motor"])
            km_a = c2.number_input("KM Actual")
            km_p = c2.number_input("¿A qué KM toca el próximo cambio?", min_value=km_a)
            st.divider()
            m_s = st.selectbox("Mecánico", ["N/A"] + mecs); m_v = st.number_input("Mano de Obra $")
            if st.form_submit_button("Guardar y Activar Alerta"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a, "km_next": km_p, "mec_name": m_s, "mec_cost": m_v
                })
                st.rerun()

    # (Directorio, Contabilidad y Personal mantienen la lógica blindada de v42)

    if st.sidebar.button("Salir"):
        st.session_state.clear(); st.rerun()
