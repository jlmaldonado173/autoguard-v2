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

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .card { background: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    .status-ok { color: #16a34a; font-weight: bold; }
    .status-err { color: #dc2626; font-weight: bold; }
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
            st.error(f"Error de Certificado: {e}")
            return None
    return firestore.client()

db = init_firebase()
# Ruta de datos compartida
app_id = "auto-guard-v2-prod"

# --- RUTAS DE BASE DE DATOS (REGLA 1) ---
def get_logs_ref():
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection("maintenance_logs")

# --- MANEJO DE SESIÓN ---
if 'session' not in st.session_state: st.session_state.session = None

# --- PANTALLA DE ACCESO ---
if st.session_state.session is None:
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite Pro</h1>", unsafe_allow_html=True)
    
    # Diagnóstico rápido en pantalla de login
    if db:
        st.write("🟢 **Estado:** Conectado a Google Cloud")
    else:
        st.write("🔴 **Estado:** Esperando configuración de Secrets")

    t1, t2 = st.tabs(["👨‍✈️ Conductores", "📊 Propietarios"])
    
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota")
            u_name = st.text_input("Tu Nombre")
            u_bus = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR"):
                st.session_state.session = {'role':'driver', 'fleet_id':f_id.upper().strip(), 'username':u_name, 'bus':u_bus}
                st.rerun()

    with t2:
        with st.form("login_owner"):
            f_new = st.text_input("Código de Flota")
            o_name = st.text_input("Nombre Dueño")
            if st.form_submit_button("GESTIONAR"):
                if db:
                    try:
                        # CREACIÓN FORZADA DE BASE DE DATOS: Esto soluciona el error NotFound
                        db.collection("artifacts").document(app_id).set({"status": "online"}, merge=True)
                        
                        # Guardar la flota
                        get_logs_ref().document(f_new.upper().strip()).set({
                            "owner": o_name, "created": datetime.now()
                        }, merge=True)
                        
                        st.session_state.session = {'role':'owner', 'fleet_id':f_new.upper().strip(), 'username':o_name, 'bus':'ADMIN'}
                        st.rerun()
                    except Exception as e:
                        if "NotFound" in str(e):
                            st.error("⚠️ Error: La base de datos Firestore no existe. Ve a Firebase Console -> Firestore Database y haz clic en 'Crear base de datos'.")
                        else:
                            st.error(f"Error: {e}")

else:
    # --- PANEL PRINCIPAL ---
    sess = st.session_state.session
    st.sidebar.title(f"👤 {sess['username']}")
    st.sidebar.write(f"Flota: {sess['fleet_id']}")
    
    menu = st.sidebar.radio("Menú", ["🏠 Dashboard", "🛠️ Reportar", "📋 Historial"])
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.session = None
        st.rerun()

    if menu == "🏠 Dashboard":
        st.header("Análisis de Flota")
        try:
            # Regla 2: Filtro manual para evitar errores de índices
            docs = get_logs_ref().stream()
            logs = [d.to_dict() for d in docs if d.to_dict().get('fleetId') == sess['fleet_id']]
            if logs:
                df = pd.DataFrame(logs)
                st.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
                st.bar_chart(df.groupby('category')['cost'].sum())
            else:
                st.info("Aún no hay reportes registrados.")
        except Exception as e:
            st.warning("Inicializando base de datos... Por favor intenta de nuevo en 10 segundos.")

    elif menu == "🛠️ Reportar":
        st.header(f"Nuevo Reporte - Unidad {sess['bus']}")
        with st.form("rep"):
            cat = st.selectbox("Categoría", ["Motor", "Frenos", "Llantas", "Luces", "Otro"])
            desc = st.text_input("Descripción")
            cost = st.number_input("Costo ($)", min_value=0.0)
            if st.form_submit_button("GUARDAR"):
                get_logs_ref().add({
                    'fleetId': sess['fleet_id'], 'busNumber': sess['bus'], 'category': cat,
                    'description': desc, 'cost': cost, 'username': sess['username'],
                    'date': datetime.now().strftime('%d/%m/%Y'), 'createdAt': datetime.now()
                })
                st.success("✅ ¡Reporte guardado!")

st.caption(f"AutoGuard Elite Pro V7.2 | Project: miflota-30356")
