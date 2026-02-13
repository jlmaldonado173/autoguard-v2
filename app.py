import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro Pro", layout="wide", page_icon="⚡")

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

# --- 3. LOGICA DE FILTRADO DE DATOS (CRÍTICO) ---
def get_fleet_data(u):
    """
    Filtra los datos según el rol:
    - Admin: Ve todo lo de la flota.
    - Driver: Solo ve lo de su bus.
    """
    query = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
    
    # Aplicar restricción de vista si es conductor
    if u['role'] == 'driver':
        query = query.where("bus", "==", str(u['bus']))
    
    docs = query.stream()
    data = [d.to_dict() | {"id": d.id} for d in docs]
    df = pd.DataFrame(data)
    
    if not df.empty:
        for c in ['mec_cost', 'sup_cost', 'mec_paid', 'sup_paid', 'km_current']:
            df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
    return df

# --- 4. ACCESO ---
if 'user' not in st.session_state:
    st.title("⚡ Itaro")
    with st.container(border=True):
        role = st.selectbox("Tipo de Acceso", ["Conductor", "Administrador/Dueño"])
        f_id = st.text_input("ID de Flota").upper().strip()
        u_name = st.text_input("Nombre")
        u_bus = st.text_input("N° de Bus")
        if st.button("ENTRAR AL SISTEMA", use_container_width=True):
            st.session_state.user = {
                'role': 'owner' if "Adm" in role else 'driver', 
                'fleet': f_id, 'name': u_name, 'bus': str(u_bus)
            }
            st.rerun()
else:
    u = st.session_state.user
    df = get_fleet_data(u)
    
    st.markdown(f"<div style='background:#0f172a; color:white; padding:1rem; border-radius:10px; display:flex; justify-content:space-between; margin-bottom:20px;'><div>🛸 <b>Itaro</b> | {u['fleet']}</div><div>👤 {u['name']} ({'Admin' if u['role']=='owner' else f'Bus {u['bus']}'})</div></div>", unsafe_allow_html=True)

    # --- SIDEBAR ---
    menu = ["🏠 Inicio", "🛠️ Reportar", "📋 Deudas", "⛽ Gas", "🏢 Directorio"]
    choice = st.sidebar.radio("Menú", menu)
    if st.sidebar.button("Cerrar Sesión"):
        del st.session_state.user
        st.rerun()

    # --- VISTA: INICIO (DASHBOARD PRIVADO) ---
    if choice == "🏠 Inicio":
        st.subheader("Resumen de Estado")
        if not df.empty:
            df['deuda'] = (df['mec_cost'] + df['sup_cost']) - (df['mec_paid'] + df['sup_paid'])
            
            c1, c2, c3 = st.columns(3)
            # El Admin ve el total de la flota, el conductor solo su total personal
            label_gasto = "Gasto Total Flota" if u['role'] == 'owner' else "Mi Gasto Acumulado"
            label_deuda = "Deuda Total Flota" if u['role'] == 'owner' else "Mi Deuda Pendiente"
            
            c1.metric(label_gasto, f"${(df['mec_cost'].sum() + df['sup_cost'].sum()):,.0f}")
            c2.metric(label_deuda, f"${df['deuda'].sum():,.0f}")
            
            last_km = int(df[df['bus'] == u['bus']]['km_current'].max()) if not df[df['bus'] == u['bus']].empty else 0
            c3.metric("Último KM (Mi Bus)", f"{last_km:,.0f}")

            if u['role'] == 'owner':
                st.write("### 🚩 Deuda Desglosada por Unidad")
                st.bar_chart(df.groupby('bus')['deuda'].sum())

    # --- VISTA: REPORTAR ---
    elif choice == "🛠️ Reportar":
        st.subheader("Registrar Mantenimiento")
        with st.form("f_report"):
            bus_num = u['bus'] if u['role'] == 'driver' else st.text_input("Bus", value=u['bus'])
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Motor", "Llantas", "Otros"])
            km_r = st.number_input("Kilometraje Actual", min_value=0)
            part = st.text_area("Descripción")
            
            col1, col2 = st.columns(2)
            m_name = col1.text_input("Mecánico")
            m_cost = col1.number_input("Costo Mano de Obra", min_value=0.0)
            s_name = col2.text_input("Almacén")
            s_cost = col2.number_input("Costo Repuestos", min_value=0.0)
            
            if st.form_submit_button("GUARDAR REPORTE"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": str(bus_num), "category": cat, "part": part,
                    "km_current": km_r, "mec_name": m_name, "mec_cost": m_cost, "mec_paid": 0,
                    "sup_name": s_name, "sup_cost": s_cost, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("Reporte enviado"); time.sleep(1); st.rerun()

    # --- VISTA: DEUDAS (SOLO LO PROPIO PARA CONDUCTORES) ---
    elif choice == "📋 Deudas":
        st.subheader("Cuentas Pendientes")
        # El DataFrame 'df' ya viene filtrado desde la función get_fleet_data()
        pendientes = df[(df['mec_cost'] > df['mec_paid']) | (df['sup_cost'] > df['sup_paid'])]
        
        if pendientes.empty:
            st.info("No hay deudas pendientes registradas.")
        else:
            for _, d in pendientes.iterrows():
                m_p = d['mec_cost'] - d['mec_paid']
                s_p = d['sup_cost'] - d['sup_paid']
                with st.container(border=True):
                    st.write(f"**Bus {d['bus']}** | {d['category']} ({d['date']})")
                    c1, c2 = st.columns(2)
                    if m_p > 0: 
                        c1.write(f"🔧 {d['mec_name']}: **${m_p:,.0f}**")
                    if s_p > 0: 
                        c2.write(f"🏢 {d['sup_name']}: **${s_p:,.0f}**")
                    
                    if u['role'] == 'owner':
                        # Solo el dueño ve botones de pago
                        with st.expander("Registrar Pago"):
                            abono = st.number_input("Monto", key=f"ab_{d['id']}")
                            tipo = st.radio("Destino", ["Mecánico", "Almacén"], key=f"t_{d['id']}")
                            if st.button("Confirmar Pago", key=f"btn_{d['id']}"):
                                field = "mec_paid" if tipo == "Mecánico" else "sup_paid"
                                DATA_REF.collection("logs").document(d['id']).update({field: firestore.Increment(abono)})
                                st.rerun()

    # --- VISTA: DIRECTORIO (AHORA PARA TODOS) ---
    elif choice == "🏢 Directorio":
        st.subheader("Mecánicos y Proveedores")
        
        # Cualquier usuario puede registrar un nuevo mecánico
        with st.expander("➕ Registrar Nuevo Mecánico/Proveedor"):
            name = st.text_input("Nombre/Taller")
            phone = st.text_input("WhatsApp (ej: 593999...)")
            if st.button("Guardar en Directorio"):
                if name and phone:
                    DATA_REF.collection("providers").add({
                        "name": name, "phone": phone, "fleetId": u['fleet'], "added_by": u['name']
                    })
                    st.success("Añadido correctamente")
                    st.rerun()

        # Listado de contactos de la flota
        provs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        for p in provs:
            pd = p.to_dict()
            col_p, col_b = st.columns([3, 1])
            col_p.write(f"👤 **{pd['name']}**")
            col_b.link_button("WhatsApp", f"https://wa.me/{pd['phone']}")

    elif choice == "⛽ Gas":
        # (Se mantiene igual pero con el filtro automático por bus)
        st.subheader("Registro de Combustible")
        with st.form("gas_f"):
            costo = st.number_input("Monto $", min_value=0.0)
            if st.form_submit_button("Registrar"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "category": "Gas",
                    "km_current": 0, "sup_cost": costo, "sup_paid": costo,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "mec_cost": 0, "mec_paid": 0
                })
                st.success("Registrado"); st.rerun()

st.caption("Itaro v17.5 | Privacidad de Datos Activada")
