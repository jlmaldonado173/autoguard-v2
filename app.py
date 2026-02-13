import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import urllib.parse

# --- CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="Itero Enterprise", layout="wide")

# Función para enviar WhatsApp
def send_whatsapp(phone, message):
    # Limpiar el teléfono (solo números)
    clean_phone = ''.join(filter(str.isdigit, str(phone)))
    encoded_msg = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded_msg}"

# --- DATABASE CORE ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
BASE_PATH = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- LÓGICA DE NEGOCIO ---
def save_master(collection, data):
    """Guarda Mecánicos o Casas Comerciales"""
    BASE_PATH.collection(collection).add(data)
    st.toast(f"✅ {collection.capitalize()} registrado")

def update_record(doc_id, updated_data):
    """Edición con permiso de dueño"""
    if st.session_state.user['role'] == 'owner':
        BASE_PATH.collection("logs").document(doc_id).update(updated_data)
        st.success("Registro actualizado")
        st.rerun()

# --- INTERFAZ ---
if 'user' not in st.session_state:
    # (Mismo login del paso anterior...)
    st.title("⚡ Itero Enterprise Login")
    # ... código de login ...
    # Asegúrate de capturar 'role', 'fleet', 'bus' y 'name'
else:
    u = st.session_state.user
    
    with st.sidebar:
        st.title(f"🚀 {u['fleet']}")
        tabs = ["🏠 Dashboard", "📋 Gestión Pagos", "🏢 Proveedores", "⚙️ Admin"]
        if u['role'] == 'driver':
            tabs = ["🏠 Mi Unidad", "📋 Mis Cuentas"]
        choice = st.radio("Menú", tabs)

    # --- VISTA: GESTIÓN DE PROVEEDORES (SOLO DUEÑO) ---
    if choice == "🏢 Proveedores":
        st.subheader("Maestro de Mecánicos y Casas Comerciales")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("➕ Registrar Nuevo"):
                tipo = st.selectbox("Tipo", ["Mecánico", "Casa Comercial"])
                p_name = st.text_input("Nombre / Razón Social")
                p_phone = st.text_input("WhatsApp (Ejem: 57310...)")
                if st.button("Guardar Proveedor"):
                    save_master("providers", {"name": p_name, "phone": p_phone, "type": tipo, "fleetId": u['fleet']})
        
        # Listado de proveedores
        prov_ref = BASE_PATH.collection("providers").where("fleetId", "==", u['fleet']).stream()
        prov_list = [{"id": p.id, **p.to_dict()} for p in prov_ref]
        if prov_list:
            st.table(pd.DataFrame(prov_list)[['name', 'type', 'phone']])

    # --- VISTA: GESTIÓN DE PAGOS Y ABONOS ---
    elif "Cuentas" in choice or "Pagos" in choice:
        st.subheader("Control de Deudas y Abonos")
        
        # Filtro de seguridad: Si es conductor, solo ve su bus
        query = BASE_PATH.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver':
            query = query.where("bus", "==", u['bus'])
        
        logs = query.stream()
        
        for doc in logs:
            data = doc.to_dict()
            doc_id = doc.id
            
            # Cálculo de deudas
            m_debt = data.get('mec_cost', 0) - data.get('mec_paid', 0)
            s_debt = data.get('sup_cost', 0) - data.get('sup_paid', 0)
            
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.markdown(f"**Bus {data['bus']}** | {data['category']}\n\n*{data['part']}*")
                
                # Gestión de Mecánico
                with c2:
                    st.write(f"🔧 {data.get('mec_name')}")
                    st.caption(f"Deuda: ${m_debt:,.0f}")
                    if m_debt > 0 and u['role'] == 'owner':
                        amt = st.number_input("Abono", key=f"amt_m_{doc_id}")
                        if st.button("Abonar", key=f"btn_m_{doc_id}"):
                            BASE_PATH.collection("logs").document(doc_id).update({'mec_paid': firestore.Increment(amt)})
                            st.rerun()
                
                # WhatsApp y Edición
                with c3:
                    # Botón WhatsApp
                    tel = data.get('mec_phone', "") # Debería venir del maestro
                    msg = f"Hola, soy de la flota {u['fleet']}. Sobre el arreglo del bus {data['bus']}..."
                    st.link_button("💬 WA", send_whatsapp(tel, msg))
                    
                    if u['role'] == 'owner':
                        if st.button("📝 Editar", key=f"ed_{doc_id}"):
                            st.session_state.editing = doc_id

            # Formulario de edición (Solo si el dueño presionó editar)
            if st.session_state.get('editing') == doc_id:
                with st.form(f"edit_form_{doc_id}"):
                    new_cost = st.number_input("Nuevo Costo Mecánico", value=float(data.get('mec_cost', 0)))
                    new_part = st.text_input("Descripción", value=data.get('part', ""))
                    if st.form_submit_button("Confirmar Cambios"):
                        update_record(doc_id, {"mec_cost": new_cost, "part": new_part})
                        del st.session_state.editing

    # --- VISTA: DASHBOARD INTELIGENTE ---
    elif "🏠" in choice:
        st.subheader("Estado Financiero")
        # Aquí va el código de gráficas anterior, pero filtrado
        # Si es conductor, mostrar solo su 'total_debt'
        # Si es dueño, mostrar el acumulado de todos los buses.
