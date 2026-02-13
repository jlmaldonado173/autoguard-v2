import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
from io import BytesIO
from PIL import Image
import requests
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itero Smart Care", layout="wide", page_icon="🔄")

# Colores de marca basados en tu logo
BRAND_BLUE = "#1d4e89"
BRAND_GRAY = "#94a3b8"
BRAND_GREEN = "#22c55e" # Para Frenos
BRAND_RED = "#ef4444"   # Para Caja/Urgente

CAT_CONFIG = {
    "Frenos": {"color": "#22c55e", "icon": "🛑"},
    "Caja": {"color": "#ef4444", "icon": "⚙️"},
    "Motor": {"color": "#3b82f6", "icon": "🚀"},
    "Suspensión": {"color": "#f59e0b", "icon": "🚜"},
    "Llantas": {"color": "#06b6d4", "icon": "⭕"},
    "Eléctrico": {"color": "#a855f7", "icon": "⚡"}
}

# --- 2. ESTILOS CSS PERSONALIZADOS ---
st.markdown(f"""
    <style>
    .main {{ background-color: #f1f5f9; }}
    .stButton>button {{
        border-radius: 12px;
        background-color: {BRAND_BLUE};
        color: white;
        transition: all 0.3s;
    }}
    .bus-card {{
        background: white;
        padding: 20px;
        border-radius: 20px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        border-left: 8px solid {BRAND_BLUE};
    }}
    .stat-card {{
        background: white;
        padding: 15px;
        border-radius: 15px;
        text-align: center;
        border: 1px solid #e2e8f0;
    }}
    .status-badge {{
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO ---
def get_image_base64(path_or_url):
    # Función para convertir tu logo a base64 y mostrarlo
    return "https://i.postimg.cc/mD3VfP8x/1000110802.png" # URL de ejemplo basada en tu imagen

# --- 4. LÓGICA DE NEGOCIO / FIREBASE ---
# (Asumimos que la conexión db ya existe como en tu código previo)
# get_ref("maintenance_logs"), get_ref("vendors"), get_ref("mechanics")

# --- 5. INTERFAZ DE USUARIO ---

def draw_sidebar():
    with st.sidebar:
        st.image("https://i.postimg.cc/mD3VfP8x/1000110802.png", width=180)
        st.title("Itero Pro")
        st.write(f"👤 **{st.session_state.user['name']}**")
        st.divider()
        menu = ["🏠 Panel Control", "🛠️ Nuevo Reporte", "⚖️ Comparar Precios", "👨‍🔧 Deudas y Pagos", "📅 Próximos Cambios"]
        return st.radio("Navegación", menu)

# --- PÁGINA: COMPARADOR DE PRECIOS ---
def page_comparador():
    st.header("⚖️ Comparador de Repuestos")
    st.info("Registra precios de diferentes casas comerciales para ahorrar en tu flota.")
    
    with st.expander("➕ Registrar Cotización"):
        with st.form("f_quote"):
            item = st.text_input("Nombre del Repuesto (ej. Kit de Embrague)")
            vendor = st.text_input("Casa Comercial")
            price = st.number_input("Precio $", min_value=0.0)
            if st.form_submit_button("Guardar Cotización"):
                # Lógica para guardar en Firebase col 'quotes'
                st.success("Cotización guardada")

    # Simulación de visualización
    data = {
        "Repuesto": ["Rodillo Nsk", "Rodillo Nsk", "Bomba Agua"],
        "Proveedor": ["Comercial Abad", "Repuestos Loja", "Diesel Parts"],
        "Precio": [45.00, 38.50, 120.00]
    }
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)

# --- PÁGINA: NUEVO REPORTE (CON COLORES Y SECCIONES) ---
def page_reporte():
    st.header("🛠️ Registro de Mantenimiento")
    
    with st.form("maint_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            bus = st.selectbox("Unidad", ["Bus 01", "Bus 05", "Bus 12"])
            cat = st.selectbox("Categoría de Arreglo", list(CAT_CONFIG.keys()))
            detalle = st.text_area("Descripción (Ej: Cambio de rodillos y zapatas)")
        
        with col2:
            costo_repuesto = st.number_input("Costo Repuestos $", min_value=0.0)
            pago_rep_pend = st.checkbox("¿Repuesto Pendiente de Pago?")
            
            costo_obra = st.number_input("Costo Mano de Obra $", min_value=0.0)
            pago_obra_pend = st.checkbox("¿Mecánico Pendiente de Pago?")
            
        st.divider()
        proximo_cambio = st.date_input("Notificar próximo cambio en:", datetime.now() + timedelta(days=90))
        
        if st.form_submit_button("🚀 REGISTRAR ARREGLO"):
            # Aquí guardarías en Firestore incluyendo los campos 'status_pago_rep' y 'status_pago_obra'
            st.balloons()
            st.success("Reporte guardado exitosamente.")

# --- PÁGINA: DEUDAS Y PAGOS ---
def page_deudas():
    st.header("👨‍🔧 Control de Pagos Pendientes")
    
    # Ejemplo de cómo se vería la lista de deudas
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💳 A Repuestos")
        st.warning("Total Deuda: $450.00")
        st.markdown("""
        * **Casa Comercial X**: $150 (Rodillos Bus 04) [Pagar]
        * **Importadora Y**: $300 (Kit Frenos Bus 10) [Pagar]
        """)
        
    with col2:
        st.subheader("👨‍🔧 A Mecánicos")
        st.error("Total Deuda: $120.00")
        st.markdown("""
        * **Maestro Juan**: $80 (Caja Bus 02) [Pagar]
        * **Talleres Eléctricos**: $40 (Arranque Bus 01) [Pagar]
        """)

# --- RENDERIZADO PRINCIPAL ---
if st.session_state.user:
    sel = draw_sidebar()
    
    if sel == "🏠 Panel Control":
        st.title(f"Dashboard {st.session_state.user['fleet']}")
        # Aquí irían las métricas generales
        c1, c2, c3 = st.columns(3)
        c1.metric("Gasto Mes", "$2,450", "+12%")
        c2.metric("Pendiente Pago", "$570", "-5%", delta_color="inverse")
        c3.metric("Buses Activos", "14/15")
        
    elif sel == "🛠️ Nuevo Reporte":
        page_reporte()
    elif sel == "⚖️ Comparar Precios":
        page_comparador()
    elif sel == "👨‍🔧 Deudas y Pagos":
        page_deudas()
    elif sel == "📅 Próximos Cambios":
        st.header("📅 Recordatorios de Mantenimiento")
        st.info("Próximos 30 días")
        st.write("- **Bus 05**: Cambio de aceite (En 3 días)")
        st.write("- **Bus 12**: Revisión de frenos (En 12 días)")

else:
    # Lógica de Login simplificada
    st.title("Bienvenido a Itero")
    # ... (Resto del login)
