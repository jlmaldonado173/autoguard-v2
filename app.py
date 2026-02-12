import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
from io import BytesIO
from PIL import Image
import requests

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard AI Elite V7.2", layout="wide", page_icon="🧠")

# --- ESTILOS ---
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .card { background: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 15px; }
    .error-box { background: #fee2e2; border: 2px solid #ef4444; padding: 20px; border-radius: 15px; color: #991b1b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZACIÓN DE FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred_info = json.loads(st.secrets["FIREBASE_JSON"])
                cred = credentials.Certificate(cred_info)
                firebase_admin.initialize_app(cred)
            else:
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error de Inicialización: {e}")
            return None
    return firestore.client()

db = init_firebase()

# Este ID es el "corazón" de la base de datos. 
# Si cambias este nombre, se crea una base de datos nueva y limpia.
app_id = "auto-guard-v2-prod"

# --- RUTAS DE BASE DE DATOS (REGLA 1) ---
def get_logs_ref():
    # Esta ruta sigue la jerarquía estricta: artifacts -> appId -> public -> data -> maintenance_logs
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection("maintenance_logs")

# --- SESIÓN ---
if 'session' not in st.session_state: st.session_state.session = None

# --- INTERFAZ ---
if st.session_state.session is None:
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite Pro</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "📊 Propietarios"])
    
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota (Ej: JOSE01)")
            u_name = st.text_input("Tu Nombre")
            u_bus = st.text_input("N° de Unidad")
            if st.form_submit_button("INGRESAR"):
                if f_id and u_name:
                    st.session_state.session = {'role':'driver', 'fleet_id':f_id.upper().strip(), 'username':u_name, 'bus':u_bus}
                    st.rerun()
                else: st.warning("Completa los datos.")

    with t2:
        with st.form("login_owner"):
            f_new = st.text_input("Código de Flota")
            o_name = st.text_input("Nombre del Dueño")
            if st.form_submit_button("GESTIONAR FLOTA"):
                if db:
                    try:
                        # CREACIÓN AUTOMÁTICA DE RUTA: Esto evita el error "NotFound"
                        # Escribimos un documento de configuración para asegurar que la ruta exista
                        db.collection("artifacts").document(app_id).set({"active": True}, merge=True)
                        db.collection("artifacts").document(app_id).collection("public").document("data").set({"initialized": True}, merge=True)
                        
                        # Registro de la flota específica
                        get_logs_ref().document(f_new.upper().strip()).set({
                            "owner": o_name, 
                            "created": datetime.now(),
                            "type": "fleet_root"
                        }, merge=True)
                        
                        st.session_state.session = {'role':'owner', 'fleet_id':f_new.upper().strip(), 'username':o_name, 'bus':'ADMIN'}
                        st.rerun()
                    except Exception as e:
                        if "NotFound" in str(e):
                            st.markdown(f"""
                            <div class='error-box'>
                                <h3>❌ Error de Configuración en Google</h3>
                                <p>La base de datos Firestore no ha sido creada en tu proyecto.</p>
                                <p><b>Solución:</b> Ve a Firebase Console -> Firestore Database y haz clic en el botón azul "Crear base de datos".</p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.error(f"Error: {e}")

else:
    sess = st.session_state.session
    with st.sidebar:
        st.title(f"👤 {sess['username']}")
        st.write(f"ID Flota: **{sess['fleet_id']}**")
        menu = st.radio("Menú", ["🏠 Dashboard", "🛠️ Reportar", "📋 Historial"])
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.session = None
            st.rerun()

    if menu == "🏠 Dashboard":
        st.header("Análisis de la Flota")
        try:
            # Obtenemos los logs de forma segura
            logs_stream = get_logs_ref().stream()
            logs_list = []
            # Manejamos el stream para evitar el error de iteración
            for doc in logs_stream:
                d = doc.to_dict()
                if d.get('fleetId') == sess['fleet_id']:
                    logs_list.append(d)
            
            if logs_list:
                df = pd.DataFrame(logs_list)
                st.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
                st.bar_chart(df.groupby('category')['cost'].sum())
            else:
                st.info("No hay datos todavía. Registra tu primer bus en 'Reportar'.")
        except Exception as e:
            if "NotFound" in str(e):
                st.warning("⚠️ La base de datos se está inicializando. Por favor, crea un reporte en la sección 'Reportar' para activar el sistema.")
            else:
                st.error(f"Error de lectura: {e}")

    elif menu == "🛠️ Reportar":
        st.header(f"Nuevo Reporte - Unidad {sess['bus']}")
        with st.form("form_report"):
            cat = st.selectbox("Sistema", ["Motor", "Frenos", "Suspensión", "Llantas", "Luces", "Caja", "Otro"])
            desc = st.text_input("¿Qué trabajo se realizó?")
            cost = st.number_input("Costo Total ($)", min_value=0.0)
            km = st.number_input("Kilometraje Actual", min_value=0)
            if st.form_submit_button("GUARDAR REPORTE"):
                try:
                    get_logs_ref().add({
                        'fleetId': sess['fleet_id'], 'busNumber': sess['bus'], 'category': cat,
                        'description': desc, 'mileage': km, 'cost': cost,
                        'username': sess['username'], 'date': datetime.now().strftime('%d/%m/%Y'),
                        'createdAt': datetime.now(), 'paid': False
                    })
                    st.success("✅ Reporte guardado con éxito.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

st.caption(f"AutoGuard V7.2 | Base de Datos: {app_id}")
