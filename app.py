import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itaro", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    .main-card { background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #0f172a; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 10px; }
    .stMetric { background: #f8fafc; padding: 10px; border-radius: 10px; }
    .top-bar { background: #0f172a; color: white; padding: 1rem; border-radius: 10px; display: flex; justify-content: space-between; margin-bottom: 20px; align-items: center; }
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
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. FUNCIONES DE UTILIDAD ---
def get_data(col):
    return DATA_REF.collection(col)

def send_wa(phone, msg):
    clean_phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"

def get_last_km(df, bus_id):
    if df.empty: return 0
    bus_df = df[df['bus'] == str(bus_id)]
    if bus_df.empty: return 0
    return pd.to_numeric(bus_df['km_current'], errors='coerce').max()

# --- 4. LÓGICA DE LOGIN ---
if 'user' not in st.session_state:
    st.title("⚡ Itaro")
    with st.container(border=True):
        role = st.selectbox("Tipo de Acceso", ["Administrador/Dueño", "Conductor"])
        f_id = st.text_input("ID de Flota").upper()
        u_name = st.text_input("Tu Nombre")
        u_bus = st.text_input("N° de Bus")
        if st.button("ENTRAR AL SISTEMA", use_container_width=True):
            st.session_state.user = {'role': 'owner' if "Adm" in role else 'driver', 'fleet': f_id, 'name': u_name, 'bus': u_bus}
            st.rerun()
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><div>🛸 <b>Itaro</b> | {u['fleet']}</div><div>👤 {u['name']} (Bus {u['bus']})</div></div>", unsafe_allow_html=True)

    # Carga de datos global para toda la app
    query = get_data("logs").where("fleetId", "==", u['fleet'])
    if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
    logs_raw = [l.to_dict() | {"id": l.id} for l in query.stream()]
    df = pd.DataFrame(logs_raw) if logs_raw else pd.DataFrame()

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("Menú Itaro")
        menu = ["🏠 Inicio", "🛠️ Reportar", "⛽ Gas", "📋 Historial/Abonos", "🏢 Proveedores"]
        choice = st.radio("Navegar", menu)
        if st.button("Cerrar Sesión"):
            del st.session_state.user
            st.rerun()

    # --- VISTA: INICIO ---
    if choice == "🏠 Inicio":
        st.subheader("Estado de Flota")
        if not df.empty:
            # Convertir columnas a numérico para evitar errores
            for c in ['mec_cost', 'sup_cost', 'mec_paid', 'sup_paid']: 
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            df['deuda'] = (df['mec_cost'] + df['sup_cost']) - (df['mec_paid'] + df['sup_paid'])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${(df['mec_cost'].sum() + df['sup_cost'].sum()):,.0f}")
            c2.metric("Deuda Pendiente", f"${df['deuda'].sum():,.0f}", delta_color="inverse")
            c3.metric("Último KM", f"{get_last_km(df, u['bus']):,.0f}")
            
            st.divider()
            st.write("### 🚩 Deuda por Unidad")
            st.bar_chart(df.groupby('bus')['deuda'].sum())

    # --- VISTA: REPORTAR (CON KM) ---
    elif choice == "🛠️ Reportar":
        st.subheader("Registrar Nuevo Arreglo")
        current_km = get_last_km(df, u['bus'])
        with st.form("form_report"):
            bus = st.text_input("Bus", value=u['bus'])
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Motor", "Caja", "Suspensión", "Llantas", "Otro"])
            km_report = st.number_input("Kilometraje Actual", min_value=int(current_km))
            part = st.text_area("Descripción del daño/repuesto")
            col1, col2 = st.columns(2)
            m_name = col1.text_input("Nombre Mecánico")
            m_cost = col1.number_input("Costo Mano de Obra", min_value=0.0)
            s_name = col2.text_input("Casa Comercial (Almacén)")
            s_cost = col2.number_input("Costo Repuestos", min_value=0.0)
            km_next = st.number_input("Próximo Arreglo (KM)", value=km_report + 5000 if cat == "Aceite" else 0)
            
            if st.form_submit_button("GUARDAR REPORTE"):
                new_data = {
                    "fleetId": u['fleet'], "bus": bus, "category": cat, "part": part,
                    "km_current": km_report, "km_next": km_next,
                    "mec_name": m_name, "mec_cost": m_cost, "mec_paid": 0,
                    "sup_name": s_name, "sup_cost": s_cost, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": "Pendiente"
                }
                get_data("logs").add(new_data)
                st.success("Reporte guardado correctamente")
                st.rerun()

    # --- VISTA: HISTORIAL Y ABONOS (RESTAURADO) ---
    elif choice == "📋 Historial/Abonos":
        st.subheader("Gestión de Cuentas y Abonos")
        if not df.empty:
            for d in logs_raw:
                m_pende = float(d.get('mec_cost',0)) - float(d.get('mec_paid',0))
                s_pende = float(d.get('sup_cost',0)) - float(d.get('sup_paid',0))

                if m_pende > 0 or s_pende > 0:
                    with st.container(border=True):
                        st.write(f"**Bus {d['bus']} - {d['category']}** ({d['date']})")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption(f"🔧 {d.get('mec_name','')}")
                            st.write(f"Debe: ${m_pende:,.0f}")
                            if u['role'] == 'owner':
                                abono = st.number_input("Abonar", key=f"am_{d['id']}", step=5000.0)
                                if st.button("Pagar Mecánico", key=f"bm_{d['id']}"):
                                    get_data("logs").document(d['id']).update({"mec_paid": firestore.Increment(abono)})
                                    st.rerun()
                        with col2:
                            st.caption(f"🏢 {d.get('sup_name','')}")
                            st.write(f"Debe: ${s_pende:,.0f}")
                            if u['role'] == 'owner':
                                abono_s = st.number_input("Abonar", key=f"as_{d['id']}", step=5000.0)
                                if st.button("Pagar Almacén", key=f"bs_{d['id']}"):
                                    get_data("logs").document(d['id']).update({"sup_paid": firestore.Increment(abono_s)})
                                    st.rerun()

    # --- VISTA: PROVEEDORES ---
    elif choice == "🏢 Proveedores":
        st.subheader("Directorio de Proveedores")
        with st.expander("Registrar Nuevo"):
            n = st.text_input("Nombre")
            t = st.text_input("WhatsApp")
            if st.button("Guardar"):
                get_data("providers").add({"name": n, "phone": t, "fleetId": u['fleet']})
        
        provs = get_data("providers").where("fleetId", "==", u['fleet']).stream()
        for p in provs:
            pd = p.to_dict()
            st.write(f"**{pd['name']}** - {pd['phone']}")

    # --- VISTA: GAS ---
    elif choice == "⛽ Gas":
        st.subheader("Control de Combustible")
        last_km = get_last_km(df, u['bus'])
        with st.form("gas_form"):
            km_g = st.number_input("Kilometraje Actual", min_value=int(last_km))
            costo = st.number_input("Valor Tanqueo", min_value=0.0)
            if st.form_submit_button("Registrar Gas"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas",
                    "km_current": km_g, "sup_cost": costo, "sup_paid": costo,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "part": "Combustible",
                    "mec_cost": 0, "mec_paid": 0, "sup_name": "Estación"
                })
                st.success("Tanqueo registrado")
                st.rerun()

st.caption("Itaro | Sistema de Gestión")
