import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro ERP - Fleet Security", layout="wide", page_icon="🛡️")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
# Nodo de seguridad para controlar quién es dueño de cada código de flota
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. GESTIÓN DE SESIÓN Y PERSISTENCIA ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params and "u" in params:
        # Intento de auto-login
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b")
        }
        st.rerun()

# --- 3. PANTALLA DE ACCESO (LOGIN / REGISTRO) ---
if 'user' not in st.session_state:
    st.title("⚡ Itaro | Gestión de Transporte")
    
    col_log, col_reg = st.tabs(["🔑 Ingreso de Personal", "🏗️ Registrar Nueva Flota"])

    with col_log:
        with st.container(border=True):
            st.subheader("Acceso a Unidades")
            f_id = st.text_input("Código de Flota (Ej: TRANS-SURLOJA)").upper().strip()
            u_role = st.selectbox("Tipo de Usuario", ["Conductor", "Administrador/Dueño"])
            u_name = st.text_input("Nombre y Apellido")
            u_bus = st.text_input("Número de Bus / Unidad")
            
            if st.button("VERIFICAR E INGRESAR", use_container_width=True):
                # Validar si la flota existe
                check_f = FLEETS_REF.document(f_id).get()
                if check_f.exists:
                    user_data = {
                        'role': 'owner' if "Adm" in u_role else 'driver',
                        'fleet': f_id, 'name': u_name, 'bus': u_bus
                    }
                    st.session_state.user = user_data
                    # Guardar en URL para persistencia (Recuérdame)
                    st.query_params.update({"f": f_id, "u": u_name, "b": u_bus, "r": user_data['role']})
                    st.success("Acceso concedido. Cargando sistema...")
                    time.sleep(1); st.rerun()
                else:
                    st.error("❌ Código de Flota no registrado. El Administrador debe crearla primero.")

    with col_reg:
        with st.container(border=True):
            st.subheader("Crear ID de Flota Único")
            new_f_id = st.text_input("Cree un Código de Flota").upper().strip()
            owner_name = st.text_input("Nombre del Dueño / Gerente")
            
            if st.button("REGISTRAR FLOTA Y SER DUEÑO", use_container_width=True):
                if new_f_id and owner_name:
                    # Validar si el ID ya está tomado
                    exists = FLEETS_REF.document(new_f_id).get().exists
                    if not exists:
                        FLEETS_REF.document(new_f_id).set({
                            "owner": owner_name, "created_at": datetime.now(), "status": "active"
                        })
                        st.success(f"✅ Flota {new_f_id} creada. Ahora puede ingresar en la pestaña anterior.")
                    else:
                        st.error("❌ Ese código ya pertenece a otra empresa. Elija uno diferente.")
                else:
                    st.warning("Complete los campos para registrar.")

# --- 4. SISTEMA INTERNO (SOLO SI HAY SESIÓN) ---
else:
    u = st.session_state.user
    
    # Barra de navegación lateral con info de sesión
    st.sidebar.markdown(f"""
        <div style='background-color:#1e293b; padding:15px; border-radius:10px; color:white;'>
            <small>FLOTA</small><br><b>{u['fleet']}</b><br>
            <small>USUARIO</small><br><b>{u['name']}</b><br>
            <small>UNIDAD</small><br><b>{u['bus']}</b>
        </div>
    """, unsafe_allow_html=True)
    
    menu = ["🏠 Dashboard", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    choice = st.sidebar.radio("Menú Principal", menu)

    # --- CARGA DE DATOS SEGURA ---
    def load_fleet_data():
        query = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver':
            query = query.where("bus", "==", u['bus'])
        
        logs = [l.to_dict() | {"id": l.id} for l in query.stream()]
        df = pd.DataFrame(logs)
        
        # Blindaje de columnas si el DataFrame está vacío
        if df.empty:
            return pd.DataFrame(columns=['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid'])
        
        # Asegurar tipos de datos
        for c in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
        return df

    df_main = load_fleet_data()

    if choice == "🏠 Dashboard":
        st.header(f"Panel de Control - Unidad {u['bus']}")
        if not df_main.empty:
            # Lógica de semáforos de KM que vimos antes
            latest = df_main[df_main['bus'] == u['bus']].sort_values('date', ascending=False).iloc[0]
            st.metric("Kilometraje Actual", f"{latest['km_current']:,.0f} KM")
        else:
            st.info("No hay datos registrados aún.")

    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento / Arreglo")
        with st.form("form_taller"):
            # Aquí va el formulario de ingreso de KM actual, próximo, mecánico y repuestos
            st.write("Complete los datos del arreglo...")
            if st.form_submit_button("Guardar"):
                st.success("Guardado")

    elif choice == "💰 Contabilidad":
        if u['role'] == 'owner':
            st.header("Balance General de la Flota")
            # El administrador ve todos los buses y sus deudas
            st.dataframe(df_main)
        else:
            st.header("Mi Estado de Cuenta")
            # El conductor solo ve sus deudas
            st.dataframe(df_main[df_main['bus'] == u['bus']])

    # --- BOTÓN DE SALIDA ---
    if st.sidebar.button("🚪 Cerrar Sesión Segura"):
        st.query_params.clear()
        del st.session_state.user
        st.rerun()
