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
import time
import streamlit.components.v1 as components
import urllib.parse

# --- 1. CONFIGURACIÓN ELITE ---
st.set_page_config(page_title="Itero Titanium Pro v16", layout="wide", page_icon="⚡", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4",
    "Carrocería": "#ec4899", "Otro": "#64748b"
}

# --- 2. CSS AVANZADO (NEUMORPHISM & GLASSMORPHISM) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .main-card {{
        background: white; padding: 20px; border-radius: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-left: 5px solid #0f172a;
        margin-bottom: 15px;
    }}
    .stMetric {{ background: #ffffff; padding: 15px; border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
    .top-bar {{
        background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
        color: white; padding: 1rem 2rem; border-radius: 0 0 20px 20px;
        margin-bottom: 2rem; display: flex; justify-content: space-between;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. CORE: FIREBASE & DATA ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15" # Mantenemos ID para compatibilidad

def get_collection(col_name):
    """Acceso centralizado a subcolecciones con filtrado por flota"""
    return db.collection("artifacts").document(APP_ID).collection("public").document("data").collection(col_name)

def get_fleet_data(col_name, fleet_id, bus_id=None):
    query = get_collection(col_name).where("fleetId", "==", fleet_id)
    if bus_id:
        query = query.where("bus", "==", bus_id)
    return query.stream()

# --- 4. INTELIGENCIA ARTIFICIAL (GEMINI 1.5 FLASH) ---
def call_itero_ai(data_context):
    api_key = st.secrets["GEMINI_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""Analiza estos datos de mantenimiento de flota: {data_context}.
    Identifica: 1. El bus más costoso. 2. Repuesto con mayor sobreprecio. 3. Acción correctiva urgente."""
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error en Auditoría: {str(e)}"

# --- 5. LÓGICA DE NEGOCIO ---
def handle_payment(doc_id, amount, field_to_update):
    """Actualiza abonos de forma atómica"""
    doc_ref = get_collection("logs").document(doc_id)
    doc_ref.update({field_to_update: firestore.Increment(amount)})
    st.toast(f"✅ Pago registrado de ${amount}")
    time.sleep(1)
    st.rerun()

# --- 6. INTERFAZ DE USUARIO (DASHBOARD) ---
if 'user' not in st.session_state:
    # Lógica de Login simplificada (Mantener tu lógica de query_params es buena para persistencia)
    st.title("🚀 Itero Titanium Pro")
    with st.container():
        role = st.selectbox("Tipo de Acceso", ["Conductor", "Administrador/Dueño"])
        f_id = st.text_input("ID de Flota (Ej: TRANS_NORTE)").upper()
        u_name = st.text_input("Tu Nombre")
        u_bus = st.text_input("N° de Bus (Si aplica)")
        
        if st.button("ENTRAR AL SISTEMA", use_container_width=True):
            st.session_state.user = {
                'role': 'driver' if role == "Conductor" else 'owner',
                'fleet': f_id, 'name': u_name, 'bus': u_bus
            }
            st.rerun()
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><div><b>FLOTA:</b> {u['fleet']}</div><div><b>USER:</b> {u['name']}</div></div>", unsafe_allow_html=True)

    # --- SIDEBAR MEJORADO ---
    with st.sidebar:
        st.header("Menú Principal")
        tabs = ["🏠 Inicio", "🛠️ Reportar", "⛽ Gas", "📋 Historial", "🤖 Auditor IA"]
        choice = st.radio("Navegar", tabs)

    # --- VISTA: INICIO ---
    if choice == "🏠 Inicio":
        st.subheader("Estado de la Flota")
        raw_logs = get_fleet_data("logs", u['fleet'])
        logs_list = [l.to_dict() for l in raw_logs]
        
        if logs_list:
            df = pd.DataFrame(logs_list)
            # Normalización rápida
            df['total_debt'] = (df.get('mec_cost',0) + df.get('sup_cost',0)) - (df.get('mec_paid',0) + df.get('sup_paid',0))
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${df['mec_cost'].sum() + df.get('sup_cost',0).sum():,.2f}")
            c2.metric("Deuda Pendiente", f"${df['total_debt'].sum():,.2f}", delta="-Acción Requerida", delta_color="inverse")
            c3.metric("Buses Activos", len(df['bus'].unique()))

            
            
            st.divider()
            st.write("### 🚩 Alertas por Unidad")
            # Agrupar por bus para ver deudas críticas
            debt_by_bus = df.groupby('bus')['total_debt'].sum().sort_values(ascending=False)
            st.bar_chart(debt_by_bus)

    # --- VISTA: HISTORIAL Y PAGOS ---
    elif choice == "📋 Historial":
        st.subheader("Gestión de Cuentas y Evidencias")
        raw_logs = get_fleet_data("logs", u['fleet'], u['bus'] if u['role']=='driver' else None)
        
        for doc in raw_logs:
            data = doc.to_dict()
            with st.container():
                st.markdown(f"""
                <div class='main-card'>
                    <div style='display:flex; justify-content:space-between'>
                        <b>Bus {data['bus']} - {data['category']}</b>
                        <span style='color:gray'>{data.get('date')}</span>
                    </div>
                    <p>{data['part']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                exp = st.expander("Detalle de Costos y Pagos")
                with exp:
                    col_a, col_b = st.columns(2)
                    # Lógica de Mecánico
                    m_debt = data.get('mec_cost',0) - data.get('mec_paid',0)
                    col_a.write(f"**Mecánico:** {data.get('mec_name')}")
                    col_a.write(f"Deuda: ${m_debt:,.2f}")
                    if m_debt > 0 and u['role'] == 'owner':
                        pay_m = col_a.number_input("Abonar $", key=f"pay_m_{doc.id}", min_value=0.0, max_value=float(m_debt))
                        if col_a.button("Registrar Pago", key=f"btn_m_{doc.id}"):
                            handle_payment(doc.id, pay_m, 'mec_paid')
                    
                    # Lógica de Almacén
                    s_debt = data.get('sup_cost',0) - data.get('sup_paid',0)
                    col_b.write(f"**Almacén:** {data.get('sup_name')}")
                    col_b.write(f"Deuda: ${s_debt:,.2f}")
                    if s_debt > 0 and u['role'] == 'owner':
                        pay_s = col_b.number_input("Abonar $", key=f"pay_s_{doc.id}", min_value=0.0, max_value=float(s_debt))
                        if col_b.button("Registrar Pago ", key=f"btn_s_{doc.id}"):
                            handle_payment(doc.id, pay_s, 'sup_paid')

    # --- VISTA: AUDITOR IA ---
    elif choice == "🤖 Auditor IA":
        st.subheader("Análisis Inteligente Itero")
        if st.button("EJECUTAR AUDITORÍA COMPLETA"):
            logs = [l.to_dict() for l in get_fleet_data("logs", u['fleet'])]
            if logs:
                with st.spinner("Gemini analizando patrones de gasto..."):
                    context = str(logs)[:3000] # Limitar tokens
                    analisis = call_itero_ai(context)
                    st.markdown(f"> {analisis}")
            else:
                st.warning("No hay datos suficientes para analizar.")

st.caption(f"Itero V16 Pro | Optimized for Fleet Management")
