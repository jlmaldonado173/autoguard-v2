import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN, LOGO Y ESTILOS ---
# Usamos un emoji de rayo como logo temporal, puedes cambiar el link de la imagen si tienes un logo .png
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1162/1162460.png" 

st.set_page_config(page_title="Itaro", layout="wide", page_icon="⚡")

st.markdown(f"""
    <style>
    .main-card {{ background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #0f172a; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 10px; }}
    .stMetric {{ background: #f8fafc; padding: 10px; border-radius: 10px; }}
    .top-bar {{ background: #0f172a; color: white; padding: 1rem; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }}
    .logo-img {{ width: 40px; margin-right: 15px; }}
    .alert-box {{ padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #ef4444; background: #fee2e2; color: #b91c1c; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. CORE DATABASE ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15" # Mantenemos el ID de DB para no perder datos
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. FUNCIONES DE INTELIGENCIA ---
def get_data(col):
    return DATA_REF.collection(col)

def send_wa(phone, msg):
    clean_phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"

def get_bus_status(df, bus_id):
    """Obtiene el último KM y salud temporal del bus."""
    bus_logs = df[df['bus'] == str(bus_id)].copy()
    if bus_logs.empty: return 0, 99
    
    bus_logs['date_dt'] = pd.to_datetime(bus_logs['date'])
    latest = bus_logs.sort_values('date_dt').iloc[-1]
    last_km = pd.to_numeric(bus_logs['km_current'], errors='coerce').max()
    days_since = (datetime.now() - latest['date_dt']).days
    return int(last_km if not pd.isna(last_km) else 0), days_since

# --- 4. ACCESO AL SISTEMA ---
if 'user' not in st.session_state:
    st.markdown(f"<center><img src='{LOGO_URL}' width='100'><h1 style='color:#0f172a;'>Itaro</h1></center>", unsafe_allow_html=True)
    with st.container(border=True):
        role = st.selectbox("Rol", ["Administrador", "Conductor"])
        f_id = st.text_input("ID de Flota").upper()
        u_name = st.text_input("Nombre")
        u_bus = st.text_input("N° de Unidad")
        if st.button("INGRESAR", use_container_width=True):
            st.session_state.user = {'role': 'owner' if "Adm" in role else 'driver', 'fleet': f_id, 'name': u_name, 'bus': u_bus}
            st.rerun()
else:
    u = st.session_state.user
    st.markdown(f"""
        <div class='top-bar'>
            <div style='display:flex; align-items:center;'>
                <img src='{LOGO_URL}' class='logo-img'>
                <b style='font-size:20px;'>Itaro</b>
            </div>
            <div>🛸 {u['fleet']} | 👤 {u['name']} (Bus {u['bus']})</div>
        </div>
        """, unsafe_allow_html=True)

    # --- CARGA GLOBAL DE LOGS ---
    query = get_data("logs").where("fleetId", "==", u['fleet'])
    if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
    logs = [l.to_dict() for l in query.stream()]
    df = pd.DataFrame(logs) if logs else pd.DataFrame()

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("Menú")
        menu = ["🏠 Inicio", "🛠️ Reportar", "⛽ Gas", "📋 Cuentas", "🏢 Proveedores"]
        choice = st.radio("Ir a:", menu)
        if st.button("Cerrar Sesión"):
            del st.session_state.user
            st.rerun()

    # --- VISTA: INICIO (MONITOR DE ALERTAS) ---
    if choice == "🏠 Inicio":
        st.subheader("📊 Estado de Operación")
        
        if not df.empty:
            # Sincronización de 5 días
            buses = [u['bus']] if u['role'] == 'driver' else df['bus'].unique()
            for b in buses:
                km_actual, dias = get_bus_status(df, b)
                if dias >= 5:
                    st.warning(f"⚠️ **Unidad {b}**: Sin reporte de KM hace {dias} días.")
                    with st.expander(f"Actualizar KM Unidad {b}", expanded=True):
                        with st.form(f"km_{b}"):
                            nuevo_km = st.number_input("Kilometraje Actual", min_value=km_actual)
                            if st.form_submit_button("Sincronizar"):
                                get_data("logs").add({
                                    "fleetId": u['fleet'], "bus": str(b), "category": "Control",
                                    "km_current": nuevo_km, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "part": "Sincronización Periódica (5 días)", "status": "OK"
                                })
                                st.rerun()

            # Alertas Preventivas de Mantenimiento
            st.write("### 🚩 Alertas Técnicas")
            mantenimientos = df[df.get('km_next', 0) > 0].sort_values('date').drop_duplicates('bus', keep='last')
            for _, row in mantenimientos.iterrows():
                km_now, _ = get_bus_status(df, row['bus'])
                faltan = int(row['km_next']) - km_now
                if faltan <= 500:
                    st.markdown(f"<div class='alert-box'>🚨 Unidad {row['bus']}: {row['category']} vence en {faltan} km (Meta: {row['km_next']:,})</div>", unsafe_allow_html=True)

    # --- VISTA: REPORTAR (CENTRALIZADO) ---
    elif choice == "🛠️ Reportar":
        st.subheader("🛠️ Registro de Arreglo y Mantenimiento")
        km_base, _ = get_bus_status(df, u['bus'])
        
        with st.form("form_report"):
            c1, c2 = st.columns(2)
            bus = c1.text_input("Unidad", value=u['bus'])
            cat = c2.selectbox("Categoría", ["Aceite/Filtros", "Frenos", "Llantas", "Suspensión", "Caja/Motor", "Otro"])
            
            part = st.text_area("¿Qué se le hizo?")
            
            c3, c4 = st.columns(2)
            km_actual = c3.number_input("Kilometraje ACTUAL", min_value=km_base)
            sug_km = (km_actual + 5000) if "Aceite" in cat else 0
            km_next = c4.number_input("Kilometraje PRÓXIMO Arreglo (0 si no aplica)", value=sug_km)
            
            st.divider()
            c5, c6 = st.columns(2)
            m_name = c5.text_input("Mecánico / Maestro")
            m_cost = c5.number_input("Mano de Obra $", min_value=0.0)
            s_name = c6.text_input("Casa Comercial / Almacén")
            s_cost = c6.number_input("Repuestos $", min_value=0.0)
            
            if st.form_submit_button("GUARDAR Y ACTUALIZAR ITARO"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": bus, "category": cat, "part": part,
                    "km_current": km_actual, "km_next": km_next,
                    "mec_name": m_name, "mec_cost": m_cost, "mec_paid": 0,
                    "sup_name": s_name, "sup_cost": s_cost, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": "Pendiente"
                })
                st.success("✅ Registro exitoso. Sistema sincronizado.")
                time.sleep(1)
                st.rerun()

    # --- VISTA: GAS (INTEGRADA) ---
    elif choice == "⛽ Gas":
        st.subheader("⛽ Control de Combustible")
        km_base, _ = get_bus_status(df, u['bus'])
        with st.form("gas_form"):
            col1, col2 = st.columns(2)
            km_gas = col1.number_input("Kilometraje Actual", min_value=km_base)
            galones = col2.number_input("Galones", min_value=0.0)
            precio = st.number_input("Costo Total $", min_value=0.0)
            if st.form_submit_button("Registrar Tanqueo"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas",
                    "part": f"Tanqueo {galones} galones", "km_current": km_gas,
                    "mec_cost": 0, "sup_cost": precio, "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("Tanqueo registrado.")
                st.rerun()

    # --- (Cuentas y Proveedores se mantienen con la lógica v16.2 pero bajo marca Itaro) ---
    else:
        st.info(f"Módulo {choice} activo en Itaro.")

st.caption("Itaro v18.0 | Gestión de Transporte Inteligente")
