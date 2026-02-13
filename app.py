import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro Pro v18", layout="wide", page_icon="⚡")

# --- 2. DB CORE ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. MOTOR DE DATOS FILTRADOS ---
def get_fleet_data(u):
    # Logs de mantenimiento
    query = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
    if u['role'] == 'driver':
        query = query.where("bus", "==", str(u['bus']))
    
    docs = query.stream()
    data = [d.to_dict() | {"id": d.id} for d in docs]
    df = pd.DataFrame(data)
    
    if not df.empty:
        for c in ['mec_cost', 'sup_cost', 'mec_paid', 'sup_paid', 'km_current']:
            df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
    
    # Directorio de Proveedores (Todos ven los de su flota)
    prov_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
    providers = [p.to_dict() for p in prov_docs]
    
    return df, providers

# --- 4. ACCESO ---
if 'user' not in st.session_state:
    st.title("⚡ Itaro | Gestión de Flotas")
    with st.container(border=True):
        role = st.selectbox("Tipo de Acceso", ["Conductor", "Administrador/Dueño"])
        f_id = st.text_input("ID de Flota (Ej: TRAS-LOGIC)").upper().strip()
        u_name = st.text_input("Nombre Completo")
        u_bus = st.text_input("N° de Unidad")
        if st.button("ACCEDER AL PANEL", use_container_width=True):
            if f_id and u_name and u_bus:
                st.session_state.user = {
                    'role': 'owner' if "Adm" in role else 'driver', 
                    'fleet': f_id, 'name': u_name, 'bus': str(u_bus)
                }
                st.rerun()
            else: st.error("Complete todos los campos.")
else:
    u = st.session_state.user
    df, providers = get_fleet_data(u)
    
    # UI Header
    st.markdown(f"""
        <div style='background: linear-gradient(90deg, #0f172a, #1e293b); color:white; padding:1.2rem; border-radius:12px; display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;'>
            <div style='font-size:1.2rem;'>🚀 <b>ITARO</b> | {u['fleet']}</div>
            <div style='text-align:right;'><b>{u['name']}</b><br><small>{'CONTROL TOTAL' if u['role']=='owner' else f'UNIDAD: {u['bus']}'}</small></div>
        </div>
    """, unsafe_allow_html=True)

    # --- SIDEBAR ---
    menu = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Deudas Pendientes", "⛽ Gas", "🏢 Directorio"]
    choice = st.sidebar.radio("Navegación", menu)
    st.sidebar.divider()
    if st.sidebar.button("Cerrar Sesión"):
        del st.session_state.user
        st.rerun()

    # --- VISTA: REPORTAR (CON SELECCIÓN DE MECÁNICOS) ---
    if choice == "🛠️ Reportar Arreglo":
        st.subheader("Nuevo Reporte de Mantenimiento")
        
        # Listas para los selectbox
        list_mecs = [p['name'] for p in providers] + ["Otro / Nuevo"]
        
        with st.form("main_report"):
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Categoría", ["Aceite", "Frenos", "Motor", "Suspensión", "Llantas", "Eléctrico", "Otro"])
            km_r = col2.number_input("Kilometraje Actual", min_value=0, step=1)
            
            part = st.text_area("Detalle del Repuesto o Trabajo realizado")
            
            st.markdown("---")
            c_mec, c_cost_m = st.columns([2, 1])
            m_name = c_mec.selectbox("Seleccionar Mecánico", list_mecs)
            m_cost = c_cost_m.number_input("Costo Mano Obra ($)", min_value=0.0)
            
            c_sup, c_cost_s = st.columns([2, 1])
            s_name = c_sup.selectbox("Seleccionar Almacén/Repuestos", list_mecs)
            s_cost = c_cost_s.number_input("Costo Repuestos ($)", min_value=0.0)
            
            if st.form_submit_button("REGISTRAR REPORTE", use_container_width=True):
                # Si selecciona "Otro", pero no especificó en descripción, avisar (Opcional)
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": cat, "part": part,
                    "km_current": km_r, "mec_name": m_name, "mec_cost": m_cost, "mec_paid": 0,
                    "sup_name": s_name, "sup_cost": s_cost, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("✅ Reporte guardado y actualizado en deudas."); time.sleep(1); st.rerun()

    # --- VISTA: DIRECTORIO (REGISTRO PARA TODOS) ---
    elif choice == "🏢 Directorio":
        st.subheader("Mecánicos y Almacenes de la Flota")
        
        # FORMULARIO DE INGRESO (Para conductor y admin)
        with st.expander("➕ REGISTRAR NUEVO PROVEEDOR/MECÁNICO", expanded=False):
            with st.form("new_provider"):
                new_n = st.text_input("Nombre o Razón Social")
                new_t = st.text_input("WhatsApp (Ej: 593987654321)")
                if st.form_submit_button("Guardar en la Red"):
                    if new_n and new_t:
                        DATA_REF.collection("providers").add({
                            "name": new_n, "phone": new_t, "fleetId": u['fleet']
                        })
                        st.success("Guardado. Ahora aparecerá en la lista de reportes."); time.sleep(1); st.rerun()

        # LISTADO
        if not providers:
            st.info("No hay proveedores registrados aún.")
        else:
            for p in providers:
                with st.container(border=True):
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"👷 **{p['name']}**")
                    col_b.link_button("WhatsApp", f"https://wa.me/{p['phone']}")

    # --- VISTA: DEUDAS (FILTRADO POR ROL) ---
    elif choice == "📋 Deudas Pendientes":
        st.subheader("Control de Pagos Pendientes")
        # El DataFrame 'df' ya viene filtrado desde el motor de datos
        pendientes = df[(df['mec_cost'] > df['mec_paid']) | (df['sup_cost'] > df['sup_paid'])] if not df.empty else pd.DataFrame()
        
        if pendientes.empty:
            st.success("Sin deudas pendientes registradas.")
        else:
            for _, d in pendientes.iterrows():
                m_p = d['mec_cost'] - d['mec_paid']
                s_p = d['sup_cost'] - d['sup_paid']
                with st.container(border=True):
                    st.write(f"📅 {d['date']} | **Categoría: {d['category']}**")
                    c1, c2 = st.columns(2)
                    if m_p > 0: c1.warning(f"Mecánico: {d['mec_name']}\nDebe: ${m_p:,.0f}")
                    if s_p > 0: c2.warning(f"Almacén: {d['sup_name']}\nDebe: ${s_p:,.0f}")
                    
                    if u['role'] == 'owner':
                        with st.expander("Abonar Pago"):
                            monto = st.number_input("Cantidad", key=f"amt_{d['id']}")
                            tipo = st.radio("Pagar a:", [d['mec_name'], d['sup_name']], key=f"t_{d['id']}")
                            if st.button("Registrar Pago", key=f"btn_{d['id']}"):
                                field = "mec_paid" if tipo == d['mec_name'] else "sup_paid"
                                DATA_REF.collection("logs").document(d['id']).update({field: firestore.Increment(monto)})
                                st.rerun()

    # --- VISTA: DASHBOARD ---
    elif choice == "🏠 Dashboard":
        if not df.empty:
            df['deuda'] = (df['mec_cost'] + df['sup_cost']) - (df['mec_paid'] + df['sup_paid'])
            c1, c2 = st.columns(2)
            c1.metric("Gasto Acumulado", f"${(df['mec_cost'].sum() + df['sup_cost'].sum()):,.0f}")
            c2.metric("Total en Deuda", f"${df['deuda'].sum():,.0f}", delta_color="inverse")
            
            if u['role'] == 'owner':
                st.write("### Deuda por Unidad (Visión Administrador)")
                st.bar_chart(df.groupby('bus')['deuda'].sum())
        else:
            st.info("No hay datos registrados aún.")

    # --- VISTA: GAS ---
    elif choice == "⛽ Gas":
        st.subheader("Registro de Combustible")
        with st.form("gas_f"):
            costo = st.number_input("Costo Total $", min_value=0.0)
            if st.form_submit_button("Guardar Gasto"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas",
                    "km_current": 0, "sup_cost": costo, "sup_paid": costo,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "mec_cost": 0, "mec_paid": 0,
                    "mec_name": "N/A", "sup_name": "Gasolinera"
                })
                st.success("Combustible registrado"); st.rerun()

st.caption("Itaro v18.0 | Developer Mode")
