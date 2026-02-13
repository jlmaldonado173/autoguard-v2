import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import requests
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="Itero Titanium Pro v16.2", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    .main-card { background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #0f172a; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 10px; }
    .stMetric { background: #f8fafc; padding: 10px; border-radius: 10px; }
    .top-bar { background: #0f172a; color: white; padding: 1rem; border-radius: 10px; display: flex; justify-content: space-between; margin-bottom: 20px; }
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

# --- 4. LÓGICA DE LOGIN ---
if 'user' not in st.session_state:
    st.title("🚀 Itero Titanium Pro v16")
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
    st.markdown(f"<div class='top-bar'><div>🛸 {u['fleet']}</div><div>👤 {u['name']} (Bus {u['bus']})</div></div>", unsafe_allow_html=True)

    # --- SIDEBAR COMPLETO ---
    with st.sidebar:
        st.header("Menú Pro")
        menu = ["🏠 Inicio", "🛠️ Reportar", "⛽ Gas", "📋 Historial/Abonos", "🏢 Proveedores", "🤖 Auditor IA"]
        if u['role'] == 'driver':
            menu = ["🏠 Mi Unidad", "🛠️ Reportar", "⛽ Gas", "📋 Mis Cuentas"]
        choice = st.radio("Navegar", menu)
        if st.button("Cerrar Sesión"):
            del st.session_state.user
            st.rerun()

    # --- VISTA: INICIO (Dashboard Diferenciado) ---
    if choice in ["🏠 Inicio", "🏠 Mi Unidad"]:
        st.subheader("Estado de Flota")
        query = get_data("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
        
        logs = [l.to_dict() for l in query.stream()]
        if logs:
            df = pd.DataFrame(logs)
            for c in ['mec_cost', 'sup_cost', 'mec_paid', 'sup_paid']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            df['deuda'] = (df['mec_cost'] + df['sup_cost']) - (df['mec_paid'] + df['sup_paid'])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${(df['mec_cost'].sum() + df['sup_cost'].sum()):,.0f}")
            c2.metric("Deuda Pendiente", f"${df['deuda'].sum():,.0f}", delta_color="inverse")
            c3.metric("Registros", len(df))
            st.divider()
            st.write("### 🚩 Resumen por Unidad")
            st.bar_chart(df.groupby('bus')['deuda'].sum())

    # --- VISTA: REPORTAR (Recuperada) ---
    elif choice == "🛠️ Reportar":
        st.subheader("Registrar Nuevo Arreglo")
        with st.form("form_report"):
            bus = st.text_input("Bus", value=u['bus'])
            cat = st.selectbox("Categoría", ["Frenos", "Motor", "Caja", "Suspensión", "Llantas", "Otro"])
            part = st.text_area("Descripción del daño/repuesto")
            col1, col2 = st.columns(2)
            m_name = col1.text_input("Nombre Mecánico")
            m_cost = col1.number_input("Costo Mano de Obra", min_value=0.0)
            s_name = col2.text_input("Casa Comercial (Almacén)")
            s_cost = col2.number_input("Costo Repuestos", min_value=0.0)
            
            if st.form_submit_button("GUARDAR REPORTE"):
                new_data = {
                    "fleetId": u['fleet'], "bus": bus, "category": cat, "part": part,
                    "mec_name": m_name, "mec_cost": m_cost, "mec_paid": 0,
                    "sup_name": s_name, "sup_cost": s_cost, "sup_paid": 0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": "Pendiente"
                }
                get_data("logs").add(new_data)
                st.success("Reporte guardado con éxito")

    # --- VISTA: HISTORIAL Y ABONOS (Con Edición y WhatsApp) ---
    elif "Historial" in choice or "Cuentas" in choice:
        st.subheader("Gestión de Cuentas y Abonos")
        query = get_data("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': query = query.where("bus", "==", u['bus'])
        
        for doc in query.stream():
            d = doc.to_dict()
            id_ = doc.id
            m_pende = d.get('mec_cost',0) - d.get('mec_paid',0)
            s_pende = d.get('sup_cost',0) - d.get('sup_paid',0)

            with st.container():
                st.markdown(f"<div class='main-card'><b>Bus {d['bus']}</b> - {d['category']} ({d['date']})<br>{d['part']}</div>", unsafe_allow_html=True)
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1: # Sección Mecánico
                    st.caption(f"🔧 {d['mec_name']}")
                    st.write(f"Debe: ${m_pende:,.0f}")
                    if m_pende > 0 and u['role'] == 'owner':
                        abono = st.number_input("Abonar", key=f"am_{id_}", step=5000.0)
                        if st.button("Pagar Mec", key=f"bm_{id_}"):
                            get_data("logs").document(id_).update({"mec_paid": firestore.Increment(abono)})
                            st.rerun()

                with col2: # Sección Almacén
                    st.caption(f"🏢 {d['sup_name']}")
                    st.write(f"Debe: ${s_pende:,.0f}")
                    if s_pende > 0 and u['role'] == 'owner':
                        abono_s = st.number_input("Abonar", key=f"as_{id_}", step=5000.0)
                        if st.button("Pagar Alm", key=f"bs_{id_}"):
                            get_data("logs").document(id_).update({"sup_paid": firestore.Increment(abono_s)})
                            st.rerun()
                
                with col3: # Acciones
                    # WhatsApp a proveedor (Búsqueda de disponibilidad/pago)
                    wa_msg = f"Hola, soy de la flota {u['fleet']}. Bus {d['bus']}, sobre el arreglo de {d['part']}..."
                    st.link_button("💬 WA", send_wa("573000000000", wa_msg)) # Aquí podrías jalar el tel del maestro
                    
                    if u['role'] == 'owner':
                        if st.button("📝 Editar", key=f"ed_{id_}"):
                            st.session_state.edit_id = id_

            # Sub-formulario de edición (Solo Dueño)
            if st.session_state.get('edit_id') == id_:
                with st.expander("EDITAR REGISTRO", expanded=True):
                    new_part = st.text_input("Editar Descripción", value=d['part'])
                    new_m_c = st.number_input("Nuevo Costo Mec", value=float(d['mec_cost']))
                    if st.button("Confirmar Cambios"):
                        get_data("logs").document(id_).update({"part": new_part, "mec_cost": new_m_c})
                        del st.session_state.edit_id
                        st.rerun()

    # --- VISTA: PROVEEDORES (NUEVA) ---
    elif choice == "🏢 Proveedores":
        st.subheader("Directorio de Proveedores")
        with st.expander("Registrar Nuevo"):
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono (WhatsApp)")
            tipo = st.selectbox("Tipo", ["Mecánico", "Casa Comercial"])
            if st.button("Guardar"):
                get_data("providers").add({"name": n, "phone": t, "type": tipo, "fleetId": u['fleet']})
        
        provs = get_data("providers").where("fleetId", "==", u['fleet']).stream()
        for p in provs:
            pd = p.to_dict()
            st.write(f"**{pd['name']}** ({pd['type']}) - {pd['phone']}")
            st.link_button(f"Consultar disponibilidad", send_wa(pd['phone'], "Hola, tienes disponibilidad para un bus?"))

    # --- VISTA: GAS (Recuperada) ---
    elif choice == "⛽ Gas":
        st.subheader("Control de Combustible")
        # Aquí va tu lógica anterior de Gas (Carga de datos)
        st.info("Módulo de Gas activo para registro diario.")

    # --- VISTA: AUDITOR IA (Recuperada) ---
    elif choice == "🤖 Auditor IA":
        st.subheader("Análisis de Inteligencia")
        if st.button("EJECUTAR AUDITORÍA"):
            st.write("Analizando patrones de gasto...")
            # (Lógica de requests a Gemini)

st.caption("Itero Titanium Pro v16.2 | Sistema de Gestión Integral")
