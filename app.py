import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y MARCA ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1162/1162460.png" 
st.set_page_config(page_title="Itaro Pro", layout="wide", page_icon="⚡")

st.markdown(f"""
    <style>
    .main-card {{ background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #0f172a; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 10px; }}
    .stMetric {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; }}
    .top-bar {{ background: #0f172a; color: white; padding: 1rem; border-radius: 12px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; }}
    .alert-box {{ padding: 15px; border-radius: 10px; margin-bottom: 15px; border-left: 5px solid #ef4444; background: #fee2e2; color: #b91c1c; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
DATA_REF = db.collection("artifacts").document("itero-titanium-v15").collection("public").document("data")

# --- 3. FUNCIONES CORE ---
def get_data(col): return DATA_REF.collection(col)

def get_bus_status(df, bus_id):
    if df.empty: return 0, 99
    bus_df = df[df['bus'] == str(bus_id)].copy()
    if bus_df.empty: return 0, 99
    
    bus_df['km_current'] = pd.to_numeric(bus_df['km_current'], errors='coerce').fillna(0)
    bus_df['date_dt'] = pd.to_datetime(bus_df['date'], errors='coerce')
    
    max_km = int(bus_df['km_current'].max())
    last_date = bus_df['date_dt'].max()
    days = (datetime.now() - last_date).days if pd.notnull(last_date) else 99
    return max_km, days

# --- 4. LOGIN ---
if 'user' not in st.session_state:
    st.markdown(f"<center><img src='{LOGO_URL}' width='80'><h1>Itaro</h1></center>", unsafe_allow_html=True)
    with st.container(border=True):
        role = st.selectbox("Acceso", ["Administrador", "Conductor"])
        f_id = st.text_input("ID Flota").upper()
        u_bus = st.text_input("N° Unidad")
        if st.button("ENTRAR", use_container_width=True):
            st.session_state.user = {'role': 'owner' if "Adm" in role else 'driver', 'fleet': f_id, 'bus': u_bus}
            st.rerun()
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><div><img src='{LOGO_URL}' class='logo-img'><b>Itaro</b></div><div>{u['fleet']} | Unidad {u['bus']}</div></div>", unsafe_allow_html=True)

    # Carga de Datos Sincronizada
    query = get_data("logs").where("fleetId", "==", u['fleet'])
    if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
    logs_raw = [l.to_dict() | {"id": l.id} for l in query.stream()]
    df = pd.DataFrame(logs_raw) if logs_raw else pd.DataFrame()

    menu = ["🏠 Dashboard", "🛠️ Reportar", "💰 Cuentas y Abonos", "⛽ Gas", "🏢 Proveedores"]
    choice = st.sidebar.radio("Menú", menu)

    # --- DASHBOARD + KILOMETRAJE 5 DÍAS ---
    if choice == "🏠 Dashboard":
        km_act, dias = get_bus_status(df, u['bus'])
        c1, c2 = st.columns(2)
        c1.metric("KM Actual", f"{km_act:,}")
        c2.metric("Días sin Reporte", dias)

        if dias >= 5:
            st.error(f"⚠️ ¡ALERTA! Han pasado {dias} días desde el último reporte de kilometraje.")
            with st.expander("ACTUALIZAR KILOMETRAJE AHORA", expanded=True):
                with st.form("quick_km"):
                    new_km = st.number_input("Nuevo KM", min_value=km_act)
                    if st.form_submit_button("Sincronizar"):
                        get_data("logs").add({
                            "fleetId": u['fleet'], "bus": u['bus'], "category": "Control",
                            "km_current": new_km, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "part": "Actualización de 5 días"
                        })
                        st.rerun()

    # --- REPORTAR (RESTABLECIDO) ---
    elif choice == "🛠️ Reportar":
        km_base, _ = get_bus_status(df, u['bus'])
        with st.form("f_rep"):
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Suspensión"])
            km_i = st.number_input("KM del Arreglo", min_value=km_base)
            desc = st.text_area("Descripción")
            c1, c2 = st.columns(2)
            m_n = c1.text_input("Mecánico")
            m_c = c1.number_input("Costo M.O", min_value=0.0)
            s_n = c2.text_input("Almacén")
            s_c = c2.number_input("Costo Repuestos", min_value=0.0)
            km_n = st.number_input("Próximo Cambio (KM)", value=km_i+5000 if cat=="Aceite" else 0)
            if st.form_submit_button("Guardar"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": cat, "part": desc,
                    "km_current": km_i, "km_next": km_n, "mec_name": m_n, "mec_cost": m_c,
                    "mec_paid": 0, "sup_name": s_n, "sup_cost": s_c, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("Guardado")
                st.rerun()

    # --- CUENTAS Y ABONOS (RESTABLECIDO) ---
    elif choice == "💰 Cuentas y Abonos":
        st.subheader("Control de Deudas")
        if not df.empty:
            # Asegurar que los costos sean números antes de calcular
            for col in ['mec_cost', 'mec_paid', 'sup_cost', 'sup_paid']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            for index, row in df.iterrows():
                m_debe = row['mec_cost'] - row['mec_paid']
                s_debe = row['sup_cost'] - row['sup_paid']
                
                if m_debe > 0 or s_debe > 0:
                    with st.container(border=True):
                        st.write(f"**{row['category']}** | {row['date']}")
                        st.caption(row['part'])
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"🔧 {row['mec_name']}: ${m_debe:,.0f}")
                            if u['role'] == 'owner':
                                am = st.number_input("Abonar", key=f"m_{row['id']}", step=1000.0)
                                if st.button("Pagar Mecánico", key=f"bm_{row['id']}"):
                                    get_data("logs").document(row['id']).update({"mec_paid": firestore.Increment(am)})
                                    st.rerun()
                        with c2:
                            st.write(f"🏢 {row['sup_name']}: ${s_debe:,.0f}")
                            if u['role'] == 'owner':
                                as_ = st.number_input("Abonar", key=f"s_{row['id']}", step=1000.0)
                                if st.button("Pagar Almacén", key=f"bs_{row['id']}"):
                                    get_data("logs").document(row['id']).update({"sup_paid": firestore.Increment(as_)})
                                    st.rerun()

    # --- GAS ---
    elif choice == "⛽ Gas":
        km_base, _ = get_bus_status(df, u['bus'])
        with st.form("f_gas"):
            km_g = st.number_input("KM Actual", min_value=km_base)
            costo = st.number_input("Valor Tanqueo $", min_value=0.0)
            if st.form_submit_button("Registrar Gas"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas", "km_current": km_g,
                    "sup_cost": costo, "sup_paid": costo, "sup_name": "Gasolinera",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "part": "Combustible"
                })
                st.rerun()

    # --- PROVEEDORES ---
    elif choice == "🏢 Proveedores":
        st.subheader("Directorio")
        with st.expander("Agregar Nuevo"):
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono")
            if st.button("Guardar Proveedor"):
                get_data("providers").add({"name": n, "phone": t, "fleetId": u['fleet']})
        
        provs = get_data("providers").where("fleetId", "==", u['fleet']).stream()
        for p in provs:
            pd = p.to_dict()
            st.write(f"📞 {pd['name']} - {pd['phone']}")

st.caption("Itaro v20.0 | Debugged & Ready")
