import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(page_title="Itaro ERP v33", layout="wide", page_icon="🔒")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred_dict = json.loads(st.secrets["FIREBASE_JSON"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error crítico en Firebase: {e}")
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
# Nodos de Seguridad y Datos
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. LÓGICA DE PERSISTENCIA (PARA NO PERDER LA SESIÓN) ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params and "u" in params:
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b")
        }
        st.rerun()

# --- 3. PANTALLA DE INICIO DE SESIÓN (ESTO ES LO QUE TE FALTABA) ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Acceso de Seguridad")
    
    # Pestañas para entrar o crear flota
    tab_log, tab_reg = st.tabs(["🔑 Iniciar Sesión", "🏗️ Registrar Nueva Flota"])

    with tab_log:
        with st.container(border=True):
            f_id_log = st.text_input("Código de Flota (Ej: TAXI-LOJA)").upper().strip()
            u_role = st.selectbox("Tipo de Usuario", ["Conductor", "Administrador/Dueño"])
            u_name = st.text_input("Tu Nombre")
            u_bus = st.text_input("Número de Bus/Unidad")
            
            if st.button("VERIFICAR E INGRESAR", use_container_width=True):
                if not f_id_log:
                    st.error("Ingresa el código de tu flota.")
                else:
                    # Validamos que la flota exista en la base de datos
                    if FLEETS_REF.document(f_id_log).get().exists:
                        u_data = {
                            'role': 'owner' if "Adm" in u_role else 'driver',
                            'fleet': f_id_log, 'name': u_name, 'bus': u_bus
                        }
                        st.session_state.user = u_data
                        # Guardamos en URL para que no pida login otra vez
                        st.query_params.update({"f": f_id_log, "u": u_name, "b": u_bus, "r": u_data['role']})
                        st.success("Acceso concedido...")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Código de Flota NO REGISTRADO. Ve a la pestaña de 'Registrar Nueva Flota'.")

    with tab_reg:
        st.info("Solo Dueños: Crea aquí el ID único para tu flota.")
        new_f_id = st.text_input("Crear Nuevo Código (Ej: BUS-RAPIDO)").upper().strip()
        if st.button("REGISTRAR Y SER DUEÑO", use_container_width=True):
            if new_f_id:
                if not FLEETS_REF.document(new_f_id).get().exists:
                    FLEETS_REF.document(new_f_id).set({"created_at": datetime.now(), "status": "active"})
                    st.success(f"✅ Flota '{new_f_id}' creada. Ya puedes loguearte en la pestaña anterior.")
                else:
                    st.error("❌ Ese código ya está en uso. Prueba con otro.")

# --- 4. PANEL PRINCIPAL (SOLO SE VE SI ESTÁ LOGUEADO) ---
else:
    u = st.session_state.user
    
    # Barra lateral de información
    st.sidebar.markdown(f"**Flota:** `{u['fleet']}`")
    st.sidebar.markdown(f"**Usuario:** {u['name']}")
    st.sidebar.markdown(f"**Unidad:** {u['bus']}")
    
    menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    choice = st.sidebar.radio("Navegación", menu)

    # Función para cargar proveedores (Directorio)
    def load_provs():
        docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        return [p.to_dict() | {"id": p.id} for p in docs]

    # --- MÓDULO: DIRECTORIO (LO QUE NECESITABAS) ---
    if choice == "🏢 Directorio":
        st.subheader("🏢 Directorio de Mecánicos y Comercios")
        
        with st.expander("➕ Registrar Nuevo Aliado", expanded=True):
            with st.form("new_prov"):
                c1, c2, c3 = st.columns(3)
                p_n = c1.text_input("Nombre / Local")
                p_t = c2.text_input("WhatsApp (Ej: 593...)")
                p_r = c3.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    if p_n and p_t:
                        DATA_REF.collection("providers").add({
                            "fleetId": u['fleet'], "name": p_n.upper(), "phone": p_t, "type": p_r
                        })
                        st.success("Guardado."); time.sleep(1); st.rerun()

        provs = load_provs()
        for p in provs:
            with st.container(border=True):
                col_a, col_b, col_c = st.columns([2, 2, 1])
                col_a.write(f"**{p['name']}**")
                col_a.caption(f"Tipo: {p['type']}")
                col_b.write(f"📱 {p['phone']}")
                col_c.markdown(f"[💬 Chat WA](https://wa.me/{p['phone']})")

    # --- MÓDULO: TALLER (CONEXIÓN CON DIRECTORIO) ---
    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento")
        provs = load_provs()
        mecs = [p['name'] for p in provs if p['type'] == "Mecánico"]
        coms = [p['name'] for p in provs if p['type'] == "Comercio"]
        
        with st.form("form_mant"):
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Caja", "Otro"])
            km_a = st.number_input("Kilometraje Actual", min_value=0)
            st.divider()
            c_m, c_r = st.columns(2)
            m_sel = c_m.selectbox("Mecánico", ["N/A"] + mecs)
            m_val = c_m.number_input("Costo Mano de Obra", min_value=0.0)
            r_sel = c_r.selectbox("Repuestos (Comercio)", ["N/A"] + coms)
            r_val = c_r.number_input("Costo Repuestos", min_value=0.0)
            
            if st.form_submit_button("GUARDAR REPORTE"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a,
                    "mec_name": m_sel, "mec_cost": m_val, "mec_paid": 0,
                    "com_name": r_sel, "com_cost": r_val, "com_paid": 0
                })
                st.success("Reporte guardado con éxito."); time.sleep(1); st.rerun()

    # --- BOTÓN DE SALIDA ---
    if st.sidebar.button("🚪 Cerrar Sesión Segura"):
        st.query_params.clear()
        del st.session_state.user
        st.rerun()

st.caption("Itaro v33.0 | Gestión Integral de Transporte")
