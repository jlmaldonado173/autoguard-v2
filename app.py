import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# Intentar importar Plotly (si falla, el sistema seguirá funcionando)
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro ERP", layout="wide", page_icon="🛡️")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except:
            st.error("Error en Secrets: Revisa tu FIREBASE_JSON")
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. GESTIÓN DE SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b")}
        st.rerun()

# --- 3. LOGIN Y REGISTRO SEGURO ---
if 'user' not in st.session_state:
    st.title("⚡ Itaro | Control de Flotas")
    t1, t2 = st.tabs(["Ingresar", "Registrar Nueva Flota"])
    
    with t1:
        f_id = st.text_input("ID de Flota").upper().strip()
        u_role = st.selectbox("Rol", ["Conductor", "Administrador/Dueño"])
        u_name = st.text_input("Tu Nombre")
        u_bus = st.text_input("N° de Unidad")
        if st.button("ACCEDER"):
            if FLEETS_REF.document(f_id).get().exists:
                u_data = {'role':'owner' if "Adm" in u_role else 'driver', 'fleet':f_id, 'name':u_name, 'bus':u_bus}
                st.session_state.user = u_data
                st.query_params.update({"f":f_id, "u":u_name, "b":u_bus, "r":u_data['role']})
                st.rerun()
            else: st.error("Esa flota no existe.")
            
    with t2:
        new_f = st.text_input("Crear ID (Ej: TAXI-VIP)").upper().strip()
        if st.button("CREAR MI FLOTA"):
            if not FLEETS_REF.document(new_f).get().exists:
                FLEETS_REF.document(new_f).set({"owner": "Admin", "created_at": datetime.now()})
                st.success("¡Flota Creada! Ahora ingresa en la pestaña anterior.")
            else: st.error("ID ya ocupado.")

else:
    u = st.session_state.user

    # --- 4. CARGA DE DATOS BLINDADA (EVITA EL KEYERROR) ---
    def load_safe_data():
        query = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
        
        logs = [l.to_dict() | {"id": l.id} for l in query.stream()]
        
        # Si no hay datos, devolvemos un DataFrame con las columnas mínimas para que no explote
        columns = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
        if not logs:
            return pd.DataFrame(columns=columns)
        
        df = pd.DataFrame(logs)
        # Aseguramos que todas las columnas necesarias existan
        for col in columns:
            if col not in df.columns: df[col] = 0
            
        # Forzamos conversión numérica para evitar AttributeError: pd.to_numeric
        num_cols = ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
        for nc in num_cols:
            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
        
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df

    df = load_safe_data()

    # --- 5. INTERFAZ ---
    st.sidebar.header(f"🚢 {u['fleet']}")
    menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    choice = st.sidebar.radio("Ir a:", menu)

    if choice == "🏠 Inicio":
        st.subheader(f"Estado Unidad {u['bus']}")
        if df.empty or df['km_current'].sum() == 0:
            st.info("👋 Bienvenido. Registra tu primer mantenimiento para ver el estado aquí.")
        else:
            latest = df[df['bus'] == u['bus']].sort_values('date', ascending=False)
            if not latest.empty:
                row = latest.iloc[0]
                c1, c2 = st.columns(2)
                c1.metric("KM Actual", f"{row['km_current']:,.0f}")
                if row['km_next'] > 0:
                    c2.metric("Próximo Cambio", f"En {int(row['km_next'] - row['km_current'])} KM")

    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento")
        # Cargamos categorías y proveedores previos
        provs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        p_names = [p.to_dict()['name'] for p in provs]
        
        with st.form("mant_form"):
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Caja", "Otros"])
            km_a = st.number_input("KM Actual", min_value=0)
            km_p = st.number_input("Próximo Cambio (KM)", min_value=km_a)
            st.divider()
            m_nom = st.selectbox("Mecánico", ["N/A"] + p_names)
            m_val = st.number_input("Costo Mano de Obra", min_value=0.0)
            c_nom = st.selectbox("Almacén", ["N/A"] + p_names)
            c_val = st.number_input("Costo Repuestos", min_value=0.0)
            
            if st.form_submit_button("GUARDAR"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a, "km_next": km_p,
                    "mec_name": m_nom, "mec_cost": m_val, "mec_paid": 0,
                    "com_name": c_nom, "com_cost": c_val, "com_paid": 0
                })
                st.success("Guardado"); time.sleep(1); st.rerun()

    elif choice == "💰 Contabilidad":
        st.subheader("Control Financiero")
        if df.empty:
            st.info("No hay deudas.")
        else:
            # Vista Administrador mejorada para evitar errores de cálculo
            df['deuda'] = (df['mec_cost'] - df['mec_paid']) + (df['com_cost'] - df['com_paid'])
            if u['role'] == 'owner':
                st.write("### Deuda Total por Unidad")
                if not df.empty and PLOTLY_AVAILABLE:
                    fig = px.bar(df.groupby('bus')['deuda'].sum().reset_index(), x='bus', y='deuda')
                    st.plotly_chart(fig)
                st.dataframe(df[df['deuda'] > 0][['bus', 'category', 'deuda']])
            else:
                st.write("### Mis Pendientes")
                st.dataframe(df[df['bus'] == u['bus']])

    elif choice == "🏢 Directorio":
        st.subheader("Directorio")
        with st.form("dir"):
            n = st.text_input("Nombre")
            t = st.text_input("WhatsApp")
            if st.form_submit_button("Añadir"):
                DATA_REF.collection("providers").add({"name": n, "phone": t, "fleetId": u['fleet']})
                st.rerun()

    if st.sidebar.button("Cerrar Sesión"):
        st.query_params.clear()
        del st.session_state.user
        st.rerun()
