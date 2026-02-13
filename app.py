import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# Intentar cargar Plotly para la analítica avanzada
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Itaro Titanium v36", layout="wide", page_icon="⚡")

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

# --- 2. PERSISTENCIA DE SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b")}
        st.rerun()

# --- 3. SISTEMA DE ACCESO RESTRINGIDO ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Control de Acceso Profesional")
    t1, t2 = st.tabs(["Ingresar", "Registrar Nueva Flota"])

    with t1:
        with st.container(border=True):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_name = st.text_input("Nombre de Usuario (Registrado)").upper().strip()
            u_bus = st.text_input("Unidad/Bus")
            u_role = st.selectbox("Rol", ["Conductor", "Administrador/Dueño"])
            
            if st.button("ACCEDER AL PANEL", use_container_width=True):
                fleet_doc = FLEETS_REF.document(f_id).get()
                if fleet_doc.exists:
                    auth = FLEETS_REF.document(f_id).collection("authorized_users").document(u_name).get()
                    if u_role == "Administrador/Dueño" or auth.exists:
                        u_data = {'role':'owner' if "Adm" in u_role else 'driver', 'fleet':f_id, 'name':u_name, 'bus':u_bus}
                        st.session_state.user = u_data
                        st.query_params.update({"f":f_id, "u":u_name, "b":u_bus, "r":u_data['role']})
                        st.rerun()
                    else: st.error("❌ No estás autorizado en esta flota.")
                else: st.error("❌ Flota no registrada.")

    with t2:
        with st.container(border=True):
            st.info("Solo Dueños: Cree un identificador único para su empresa.")
            new_f = st.text_input("Crear ID de Flota").upper().strip()
            adm_n = st.text_input("Nombre del Gerente/Dueño").upper().strip()
            if st.button("REGISTRAR EMPRESA"):
                if new_f and adm_n:
                    if not FLEETS_REF.document(new_f).get().exists:
                        FLEETS_REF.document(new_f).set({"owner": adm_n, "created_at": datetime.now()})
                        FLEETS_REF.document(new_f).collection("authorized_users").document(adm_n).set({"auth": True})
                        st.success(f"✅ Flota {new_f} creada. Ya puede ingresar.")
                    else: st.error("❌ ID ya en uso.")

# --- 4. PANEL OPERATIVO ---
else:
    u = st.session_state.user

    def load_all_data():
        # Proveedores
        p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        p_phones = {p['name']: p['phone'] for p in provs}
        
        # Logs Blindados (Evita KeyError)
        q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
        logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
        
        df = pd.DataFrame(logs)
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'mec_name', 'com_name']
        if df.empty: df = pd.DataFrame(columns=cols)
        for c in cols: 
            if c not in df.columns: df[c] = 0
        
        # Conversión de tipos
        for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, p_phones, df

    providers, phones, df = load_all_data()

    # --- NAVEGACIÓN ---
    st.sidebar.markdown(f"### 🚀 {u['fleet']}\n{u['name']}")
    menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio", "👥 Personal"]
    choice = st.sidebar.radio("Menú", menu if u['role'] == 'owner' else menu[:4])

    # --- MÓDULO INICIO (ESTADO PREDICTIVO) ---
    if choice == "🏠 Inicio":
        st.subheader(f"Estado de Unidad {u['bus']}")
        if not df.empty:
            bus_df = df[df['bus'] == u['bus']].sort_values('date', ascending=False)
            if not bus_df.empty:
                row = bus_df.iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric("Kilometraje Actual", f"{row['km_current']:,.0f} KM")
                km_r = row['km_next'] - row['km_current']
                c2.metric("Próximo Servicio", f"{km_r:,.0f} KM", delta=-km_r, delta_color="inverse" if km_r < 500 else "normal")
                
                days_old = (datetime.now() - row['date']).days
                c3.metric("Última Actualización", f"Hace {days_old} días")
                if days_old >= 3: st.warning("⚠️ Requiere actualizar kilometraje hoy.")

    # --- MÓDULO TALLER (REGISTRO DINÁMICO) ---
    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento / Arreglo")
        mec_list = [p['name'] for p in providers if p['type'] == "Mecánico"]
        com_list = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("form_taller"):
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Categoría", ["Motor", "Caja", "Frenos", "Llantas", "Aceite", "Eléctrico", "Otros"])
            km_a = col2.number_input("Kilometraje Actual", min_value=0)
            km_p = col2.number_input("Kilometraje Próximo Cambio", min_value=km_a)
            
            st.divider()
            c_m, c_r = st.columns(2)
            m_sel = c_m.selectbox("Mecánico (Mano de Obra)", ["N/A"] + mec_list)
            m_val = c_m.number_input("Costo Mano de Obra $", min_value=0.0)
            
            r_sel = c_r.selectbox("Comercio (Repuestos)", ["N/A"] + com_list)
            r_val = c_r.number_input("Costo Repuestos $", min_value=0.0)
            
            if st.form_submit_button("GUARDAR REGISTRO"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a, "km_next": km_p,
                    "mec_name": m_sel, "mec_cost": m_val, "mec_paid": 0,
                    "com_name": r_sel, "com_cost": r_val, "com_paid": 0
                })
                st.success("✅ Registro exitoso"); time.sleep(1); st.rerun()

    # --- MÓDULO CONTABILIDAD (ANÁLISIS DE GASTO) ---
    elif choice == "💰 Contabilidad":
        st.header("📊 Finanzas y Pagos")
        df['deuda_m'] = df['mec_cost'] - df['mec_paid']
        df['deuda_c'] = df['com_cost'] - df['com_paid']
        df['total_d'] = df['deuda_m'] + df['deuda_c']

        if u['role'] == 'owner' and PLOTLY_AVAILABLE and not df.empty:
            # Gráfico de estudio para el jefe
            fig = px.bar(df.groupby('bus')['total_d'].sum().reset_index(), x='bus', y='total_d', title="Deuda Pendiente por Unidad", color='bus')
            st.plotly_chart(fig)

        # Listado de deudas ordenadas
        for _, r in df[df['total_d'] > 0].iterrows():
            with st.container(border=True):
                st.write(f"📅 {r['date'].date()} | **Bus {r['bus']} - {r['category']}**")
                c1, c2 = st.columns(2)
                if r['deuda_m'] > 0: c1.error(f"🔧 Mecánico ({r['mec_name']}): ${r['deuda_m']:,.0f}")
                if r['deuda_c'] > 0: c2.warning(f"📦 Repuestos ({r['com_name']}): ${r['deuda_c']:,.0f}")
                
                if u['role'] == 'owner':
                    with st.expander("Abonar Pago"):
                        target = st.radio("Pagar a:", ["Mecánico", "Comercio"], key=f"t_{r['id']}")
                        monto = st.number_input("Monto $", key=f"v_{r['id']}")
                        if st.button("Confirmar Pago", key=f"b_{r['id']}"):
                            field = "mec_paid" if target == "Mecánico" else "com_paid"
                            DATA_REF.collection("logs").document(r['id']).update({field: firestore.Increment(monto)})
                            # Enlace de WhatsApp automático
                            p_name = r['mec_name'] if target == "Mecánico" else r['com_name']
                            tel = phones.get(p_name, "")
                            msg = f"Hola {p_name}, Itaro le informa un abono de ${monto:,.0f} por {r['category']} de la Unidad {r['bus']}."
                            st.markdown(f"[📲 Avisar por WhatsApp](https://wa.me/{tel}?text={urllib.parse.quote(msg)})")
                            st.rerun()

    # --- MÓDULO PERSONAL (AUTORIZACIONES) ---
    elif choice == "👥 Personal" and u['role'] == 'owner':
        st.subheader("Control de Acceso de Conductores")
        with st.form("auth_form"):
            new_u = st.text_input("Nombre Completo del Conductor").upper().strip()
            if st.form_submit_button("AUTORIZAR INGRESO"):
                FLEETS_REF.document(u['fleet']).collection("authorized_users").document(new_u).set({"auth": True})
                st.success(f"{new_u} ya puede acceder.")

    # --- MÓDULO DIRECTORIO ---
    elif choice == "🏢 Directorio":
        st.subheader("Directorio de Proveedores")
        with st.expander("➕ Añadir Nuevo"):
            with st.form("add_dir"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); tp = st.radio("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    DATA_REF.collection("providers").add({"name":n, "phone":t, "type":tp, "fleetId":u['fleet']})
                    st.rerun()
        for p in providers:
            st.write(f"**{p['type']}**: {p['name']} | 📱 {p['phone']}")

    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.query_params.clear()
        del st.session_state.user
        st.rerun()
