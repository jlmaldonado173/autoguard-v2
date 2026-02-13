import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y ESTILOS ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1162/1162460.png" 
st.set_page_config(page_title="Itaro Pro", layout="wide", page_icon="⚡")

st.markdown(f"""
    <style>
    .main-card {{ background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #0f172a; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 10px; }}
    .stMetric {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; }}
    .top-bar {{ background: #0f172a; color: white; padding: 1rem; border-radius: 12px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; }}
    .logo-img {{ width: 35px; margin-right: 12px; }}
    .alert-box {{ padding: 15px; border-radius: 10px; margin-bottom: 15px; border-left: 5px solid #ef4444; background: #fee2e2; color: #b91c1c; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE CORE ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. FUNCIONES MAESTRAS ---
def get_data(col): return DATA_REF.collection(col)

def get_bus_status(df, bus_id):
    bus_logs = df[df['bus'] == str(bus_id)].copy()
    if bus_logs.empty: return 0, 99
    bus_logs['date_dt'] = pd.to_datetime(bus_logs['date'])
    latest = bus_logs.sort_values('date_dt').iloc[-1]
    last_km = pd.to_numeric(bus_logs['km_current'], errors='coerce').max()
    days_since = (datetime.now() - latest['date_dt']).days
    return int(last_km if not pd.isna(last_km) else 0), days_since

# --- 4. SISTEMA DE ACCESO ---
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
    st.markdown(f"<div class='top-bar'><div><img src='{LOGO_URL}' class='logo-img'><b>Itaro</b></div><div>🛸 {u['fleet']} | Unidad {u['bus']}</div></div>", unsafe_allow_html=True)

    # --- CARGA DE DATOS ---
    query = get_data("logs").where("fleetId", "==", u['fleet'])
    if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
    logs_raw = [l.to_dict() | {"id": l.id} for l in query.stream()]
    df = pd.DataFrame(logs_raw) if logs_raw else pd.DataFrame()

    with st.sidebar:
        choice = st.radio("Menú", ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Cuentas/Abonos", "⛽ Gas", "🏢 Proveedores"])
        if st.button("Salir"):
            del st.session_state.user
            st.rerun()

    # --- 1. DASHBOARD (MÉTRICAS v16.2 RECARGADAS) ---
    if choice == "🏠 Dashboard":
        if not df.empty:
            # Cálculos Financieros
            for c in ['mec_cost', 'sup_cost', 'mec_paid', 'sup_paid']: 
                df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
            
            total_gasto = df['mec_cost'].sum() + df['sup_cost'].sum()
            total_pago = df['mec_paid'].sum() + df['sup_paid'].sum()
            deuda = total_gasto - total_pago
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Histórico", f"${total_gasto:,.0f}")
            c2.metric("Deuda Actual", f"${deuda:,.0f}", delta="-Pendiente", delta_color="inverse")
            
            km_act, dias = get_bus_status(df, u['bus'])
            c3.metric("Último KM", f"{km_act:,}")

            if dias >= 5:
                st.markdown(f"<div class='alert-box'>⚠️ Unidad {u['bus']} requiere actualización de KM (Hace {dias} días)</div>", unsafe_allow_html=True)
            
            st.write("### 📈 Gastos por Categoría")
            st.bar_chart(df.groupby('category')[['mec_cost', 'sup_cost']].sum())

    # --- 2. REPORTAR (CON KM PREVENTIVO) ---
    elif choice == "🛠️ Reportar Arreglo":
        st.subheader("🛠️ Registro Técnico")
        km_base, _ = get_bus_status(df, u['bus'])
        with st.form("rep_form"):
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Tipo", ["Aceite", "Frenos", "Llantas", "Motor", "Suspensión", "Eléctrico", "Otro"])
            km_in = c2.number_input("Kilometraje Actual", min_value=km_base)
            desc = st.text_area("Descripción del trabajo")
            
            c3, c4 = st.columns(2)
            m_n = c3.text_input("Mecánico")
            m_c = c3.number_input("Mano de Obra $", min_value=0.0)
            s_n = c4.text_input("Almacén")
            s_c = c4.number_input("Repuestos $", min_value=0.0)
            
            km_prox = st.number_input("Programar Próximo Cambio (KM)", value=km_in+5000 if cat=="Aceite" else 0)
            
            if st.form_submit_button("GUARDAR REGISTRO"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": cat, "part": desc,
                    "km_current": km_in, "km_next": km_prox, "mec_name": m_n, "mec_cost": m_c,
                    "mec_paid": 0, "sup_name": s_n, "sup_cost": s_c, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("✅ Guardado y Sincronizado")
                st.rerun()

    # --- 3. CUENTAS (ABONOS + EDICIÓN v16.2) ---
    elif choice == "📋 Cuentas/Abonos":
        st.subheader("💰 Gestión de Pagos")
        if not df.empty:
            for d in logs_raw:
                # Lógica de Deuda
                m_d = float(d.get('mec_cost',0)) - float(d.get('mec_paid',0))
                s_d = float(d.get('sup_cost',0)) - float(d.get('sup_paid',0))
                
                if m_d > 0 or s_d > 0:
                    with st.container(border=True):
                        st.write(f"**{d['category']}** | {d['date']}")
                        st.caption(d['part'])
                        col1, col2, col3 = st.columns([2,2,1])
                        
                        with col1:
                            st.write(f"🔧 {d['mec_name']}: **${m_d:,.0f}**")
                            if u['role'] == 'owner':
                                am = st.number_input("Abono Mec", key=f"m_{d['id']}", step=5000.0)
                                if st.button("Pagar", key=f"bm_{d['id']}"):
                                    get_data("logs").document(d['id']).update({"mec_paid": firestore.Increment(am)})
                                    st.rerun()
                        
                        with col2:
                            st.write(f"🏢 {d['sup_name']}: **${s_d:,.0f}**")
                            if u['role'] == 'owner':
                                ass = st.number_input("Abono Alm", key=f"s_{d['id']}", step=5000.0)
                                if st.button("Pagar", key=f"bs_{d['id']}"):
                                    get_data("logs").document(d['id']).update({"sup_paid": firestore.Increment(ass)})
                                    st.rerun()
                                    
                        with col3:
                            if u['role'] == 'owner':
                                if st.button("📝 Editar", key=f"ed_{d['id']}"):
                                    st.session_state.edit_id = d['id']

            # Modal de Edición
            if 'edit_id' in st.session_state:
                with st.expander("EDITAR REGISTRO", expanded=True):
                    new_p = st.text_input("Nueva descripción")
                    if st.button("Confirmar"):
                        get_data("logs").document(st.session_state.edit_id).update({"part": new_p})
                        del st.session_state.edit_id
                        st.rerun()

    # --- 4. GAS (CONTROL DE CONSUMO) ---
    elif choice == "⛽ Gas":
        st.subheader("⛽ Control de Combustible")
        km_base, _ = get_bus_status(df, u['bus'])
        with st.form("gas_f"):
            c1, c2 = st.columns(2)
            km_g = c1.number_input("Kilometraje", min_value=km_base)
            val = c2.number_input("Valor Pagado $", min_value=0.0)
            if st.form_submit_button("Registrar Gasto Gas"):
                get_data("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas",
                    "km_current": km_g, "sup_cost": val, "sup_paid": val, # Gas siempre se paga de una
                    "sup_name": "Estación Gas", "part": "Tanqueo Combustible",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("⛽ Gas registrado")
                st.rerun()

    # --- 5. PROVEEDORES ---
    elif choice == "🏢 Proveedores":
        st.subheader("🏢 Directorio de Contactos")
        with st.expander("Registrar Nuevo"):
            n = st.text_input("Nombre")
            t = st.text_input("WhatsApp (Ej: 57300...)")
            tipo = st.selectbox("Tipo", ["Mecánico", "Almacén"])
            if st.button("Guardar"):
                get_data("providers").add({"name": n, "phone": t, "type": tipo, "fleetId": u['fleet']})
        
        provs = get_data("providers").where("fleetId", "==", u['fleet']).stream()
        for p in provs:
            pd = p.to_dict()
            st.write(f"📞 **{pd['name']}** ({pd['type']}) - {pd['phone']}")
            wa_msg = urllib.parse.quote(f"Hola {pd['name']}, necesito una consulta para el bus {u['bus']}")
            st.markdown(f"[💬 Enviar WhatsApp](https://wa.me/{pd['phone']}?text={wa_msg})")

st.caption("Itaro v19.0 | El estándar de oro en gestión de transporte")
