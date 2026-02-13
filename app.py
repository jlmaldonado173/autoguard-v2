import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# Intentar cargar Plotly de forma segura (corrige error de la Imagen 1)
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Itaro ERP v34", layout="wide", page_icon="🛡️")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred_dict = json.loads(st.secrets["FIREBASE_JSON"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error crítico en Firebase: {e}")
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
# Nodos de base de datos
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. LÓGICA DE PERSISTENCIA ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params and "u" in params:
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b")
        }
        st.rerun()

# --- 3. SISTEMA DE ACCESO (LOGIN Y REGISTRO) ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Acceso de Seguridad")
    tab_log, tab_reg = st.tabs(["🔑 Iniciar Sesión", "🏗️ Registrar Nueva Flota"])

    with tab_log:
        with st.container(border=True):
            f_id_log = st.text_input("Código de Flota").upper().strip()
            u_role = st.selectbox("Rol", ["Conductor", "Administrador/Dueño"])
            u_name = st.text_input("Nombre Usuario")
            u_bus = st.text_input("N° de Unidad")
            if st.button("VERIFICAR E INGRESAR", use_container_width=True):
                if FLEETS_REF.document(f_id_log).get().exists:
                    u_data = {'role':'owner' if "Adm" in u_role else 'driver', 'fleet':f_id_log, 'name':u_name, 'bus':u_bus}
                    st.session_state.user = u_data
                    st.query_params.update({"f": f_id_log, "u": u_name, "b": u_bus, "r": u_data['role']})
                    st.rerun()
                else:
                    st.error("❌ Flota no registrada. Primero créala en la pestaña de al lado.")

    with tab_reg:
        new_f = st.text_input("Crear Nuevo Código de Flota").upper().strip()
        if st.button("CREAR FLOTA", use_container_width=True):
            if new_f and not FLEETS_REF.document(new_f).get().exists:
                FLEETS_REF.document(new_f).set({"created_at": datetime.now(), "status": "active"})
                st.success(f"✅ Flota '{new_f}' registrada. Ya puedes ingresar.")
            else: st.error("ID no válido o ya ocupado.")

# --- 4. MOTOR DE DATOS BLINDADO (Corrige errores de las imágenes 2, 3, 5 y 6) ---
else:
    u = st.session_state.user

    def load_safe_data():
        # Carga de Logs
        q_logs = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': q_logs = q_logs.where("bus", "==", u['bus'])
        logs = [l.to_dict() | {"id": l.id} for l in q_logs.stream()]
        
        # Carga de Proveedores (Para el error de la Imagen 6)
        q_provs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = [p.to_dict() | {"id": p.id} for p in q_provs]
        
        # Estructura segura de Logs
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
        if not logs:
            df_logs = pd.DataFrame(columns=cols)
        else:
            df_logs = pd.DataFrame(logs)
            for c in cols:
                if c not in df_logs.columns: df_logs[c] = 0
            # Forzado numérico (Corrige Imagen 3)
            num_cols = ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
            for nc in num_cols:
                df_logs[nc] = pd.to_numeric(df_logs[nc], errors='coerce').fillna(0)
            df_logs['date'] = pd.to_datetime(df_logs['date'], errors='coerce')

        return df_logs, provs

    df, providers = load_safe_data()

    # --- 5. NAVEGACIÓN ---
    st.sidebar.markdown(f"**Flota:** `{u['fleet']}`\n**Usuario:** {u['name']}")
    menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    choice = st.sidebar.radio("Ir a:", menu)

    if choice == "🏠 Inicio":
        st.subheader(f"Estado Unidad {u['bus']}")
        if df.empty:
            st.info("👋 Sin datos. Registra tu primer mantenimiento.")
        else:
            st.metric("KM Actual", f"{df['km_current'].max():,.0f}")

    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento")
        # Filtrado seguro de proveedores (Corrige Imagen 6)
        mecs = [p['name'] for p in providers if p.get('type') == "Mecánico"]
        coms = [p['name'] for p in providers if p.get('type') == "Comercio"]
        
        with st.form("form_mant_fix"):
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Caja", "Otro"])
            km_a = st.number_input("Kilometraje Actual", min_value=0)
            st.divider()
            c_m, c_c = st.columns(2)
            m_sel = c_m.selectbox("Mecánico", ["N/A"] + mecs)
            m_val = c_m.number_input("Costo Mano de Obra", min_value=0.0)
            c_sel = c_c.selectbox("Comercio Repuestos", ["N/A"] + coms)
            c_val = c_c.number_input("Costo Repuestos", min_value=0.0)
            
            if st.form_submit_button("GUARDAR"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a,
                    "mec_name": m_sel, "mec_cost": m_val, "mec_paid": 0,
                    "com_name": c_sel, "com_cost": c_val, "com_paid": 0
                })
                st.success("✅ Guardado."); time.sleep(1); st.rerun()

    elif choice == "🏢 Directorio":
        st.subheader("Directorio de Proveedores")
        with st.form("new_p"):
            n = st.text_input("Nombre / Taller")
            t = st.text_input("WhatsApp (593...)")
            type_p = st.radio("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Registrar"):
                DATA_REF.collection("providers").add({"name":n, "phone":t, "type":type_p, "fleetId":u['fleet']})
                st.rerun()
        for p in providers:
            st.write(f"**{p.get('type','')}**: {p['name']} - {p['phone']}")

    if st.sidebar.button("Cerrar Sesión"):
        st.query_params.clear()
        del st.session_state.user
        st.rerun()
