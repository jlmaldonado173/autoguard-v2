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
import time
import streamlit.components.v1 as components

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard Elite V1.5 - Ultimate", layout="wide", page_icon="🚌")

# --- ESTILOS CSS PREMIUM ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f8fafc; }
    
    /* Tarjetas */
    .card { background: white; padding: 24px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .metric-container { display: flex; justify-content: space-between; gap: 10px; }
    
    /* Alertas */
    .alert-critical { background: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 8px; color: #991b1b; margin-bottom: 10px; }
    .alert-warning { background: #fffbeb; border-left: 5px solid #f59e0b; padding: 15px; border-radius: 8px; color: #92400e; margin-bottom: 10px; }
    
    /* IA Response */
    .ai-box { background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); border: 2px solid #3b82f6; padding: 25px; border-radius: 20px; color: #1e3a8a; position: relative; }
    
    /* Botones */
    .stButton>button { border-radius: 10px; transition: all 0.3s; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    </style>
    """, unsafe_allow_html=True)

# --- PUENTE DE PERSISTENCIA (JS) ---
def session_persistence_js():
    components.html("""
        <script>
        const storedUser = window.localStorage.getItem('autoguard_pro_user');
        if (storedUser && !window.parent.location.search.includes('session=')) {
            const data = encodeURIComponent(storedUser);
            window.parent.location.search = '?session=' + data;
        }
        </script>
    """, height=0)

def save_session_js(data):
    json_data = json.dumps(data)
    components.html(f"""
        <script>
        window.localStorage.setItem('autoguard_pro_user', '{json_data}');
        </script>
    """, height=0)

def clear_session_js():
    components.html("""
        <script>
        window.localStorage.removeItem('autoguard_pro_user');
        window.parent.location.search = '';
        </script>
    """, height=0)

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
            st.error(f"Error de Conexión: {e}")
            return None
    return firestore.client()

db = init_firebase()
app_id = "auto-guard-v2-prod"
apiKey = "" # Gemini API

# --- RUTAS FIRESTORE ---
def get_ref(collection_name):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(collection_name)

# --- FUNCIONES DE IA ---
def call_gemini(data_summary):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    prompt = f"""
    Eres el consultor experto de AutoGuard Elite. Analiza estos datos de mantenimiento, repuestos y mecánicos:
    {data_summary}
    
    Responde en español de forma ejecutiva:
    1. Análisis de eficiencia: ¿Qué mecánicos son mejores para cada sistema?
    2. Alerta de costos: ¿Qué bus está gastando más de lo normal?
    3. Gestión de inventario: ¿Qué repuestos faltan?
    4. Plan preventivo: 3 acciones para reducir costos el próximo mes.
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for i in range(5):
        try:
            res = requests.post(url, json=payload)
            if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text']
        except: time.sleep(2**i)
    return "IA en mantenimiento. Reintenta pronto."

# --- PROCESAMIENTO DE IMAGEN ---
def process_img(file):
    if not file: return None
    img = Image.open(file)
    img.thumbnail((500, 500))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode()

# --- MANEJO DE SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None

# Recuperar sesión de URL
if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass

if st.session_state.user is None: session_persistence_js()

# --- INTERFAZ DE ACCESO ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center; color:#1e293b; margin-bottom:0;'>🚌 AutoGuard Elite</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#64748b;'>Ultimate Fleet Management V1.5</p>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Personal Operativo", "🛡️ Administración"])
    
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota")
            u_name = st.text_input("Nombre")
            u_bus = st.text_input("N° de Bus")
            rem = st.checkbox("Recordarme en este dispositivo")
            if st.form_submit_button("Ingresar"):
                data = {'role':'driver', 'fleet':f_id.upper(), 'name':u_name, 'bus':u_bus}
                st.session_state.user = data
                if rem: save_session_js(data)
                st.rerun()
                
    with t2:
        with st.form("login_owner"):
            f_owner = st.text_input("Código de Flota")
            o_name = st.text_input("Nombre Administrador")
            rem_o = st.checkbox("Mantener sesión administrativa")
            if st.form_submit_button("Acceso Total"):
                data = {'role':'owner', 'fleet':f_owner.upper(), 'name':o_name}
                st.session_state.user = data
                if rem_o: save_session_js(data)
                st.rerun()

else:
    u = st.session_state.user
    with st.sidebar:
        st.markdown(f"### 👤 {u['name']}")
        st.markdown(f"**Flota:** `{u['fleet']}`")
        st.divider()
        
        if u['role'] == 'owner':
            menu = st.radio("MENÚ PRINCIPAL", ["🏠 Dashboard", "👨‍🔧 Mecánicos", "📦 Repuestos", "📋 Historial", "🧠 Auditoría IA"])
        else:
            menu = st.radio("MENÚ", ["🛠️ Reportar Daño", "📋 Mis Reportes"])
            
        st.divider()
        if st.button("🚪 Cerrar Sesión"):
            clear_session_js()
            st.session_state.user = None
            st.rerun()

    # --- LÓGICA: DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.header("📈 Estado de la Flota")
        
        # Obtener datos
        logs = [d.to_dict() for d in get_ref("maintenance_logs").stream() if d.to_dict().get('fleetId') == u['fleet']]
        stock = [d.to_dict() for d in get_ref("inventory").stream() if d.to_dict().get('fleetId') == u['fleet']]
        
        # Alertas Dinámicas
        if stock:
            low_stock = [i for i in stock if i['quantity'] <= i['min_stock']]
            for item in low_stock:
                st.markdown(f"<div class='alert-warning'>⚠️ <b>Repuesto Bajo:</b> Quedan pocas {item['item']}. Stock actual: {item['quantity']}</div>", unsafe_allow_html=True)

        if logs:
            df = pd.DataFrame(logs)
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            with col2: st.metric("Mantenimientos", len(df))
            with col3: st.metric("Unidades", len(df['busNumber'].unique()))
            
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("Gastos por Categoría")
            st.bar_chart(df.groupby('category')['cost'].sum())
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Sin datos suficientes para mostrar estadísticas.")

    # --- LÓGICA: MECÁNICOS ---
    elif menu == "👨‍🔧 Mecánicos":
        st.header("Directorio de Especialistas")
        with st.expander("🆕 Registrar Mecánico"):
            with st.form("form_mec"):
                m_n = st.text_input("Nombre")
                m_t = st.text_input("WhatsApp")
                m_e = st.multiselect("Especialidad", ["Motor", "Frenos", "Suspensión", "Llantas", "Electricidad", "Latonería"])
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId': u['fleet'], 'name': m_n, 'phone': m_t, 'specialties': m_e})
                    st.success("Mecánico registrado")
                    st.rerun()
        
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in mecs:
            st.markdown(f"""
            <div class='card'>
                <h4>{m['name']}</h4>
                <p>📞 {m['phone']} | 🛠️ {', '.join(m['specialties'])}</p>
            </div>
            """, unsafe_allow_html=True)

    # --- LÓGICA: REPUESTOS ---
    elif menu == "📦 Repuestos":
        st.header("Inventario de Bodega")
        with st.expander("➕ Añadir Repuesto"):
            with st.form("form_inv"):
                it = st.text_input("Nombre del Repuesto")
                qt = st.number_input("Cantidad", min_value=0)
                mn = st.number_input("Mínimo de Alerta", min_value=1)
                if st.form_submit_button("Añadir"):
                    get_ref("inventory").add({'fleetId':u['fleet'], 'item':it, 'quantity':qt, 'min_stock':mn})
                    st.success("Inventario actualizado")
                    st.rerun()
        
        stock = [d.to_dict() for d in get_ref("inventory").stream() if d.to_dict().get('fleetId') == u['fleet']]
        if stock:
            st.table(pd.DataFrame(stock)[['item', 'quantity', 'min_stock']])

    # --- LÓGICA: REPORTAR (CONDUCTOR) ---
    elif menu == "🛠️ Reportar Daño":
        st.header(f"Nuevo Reporte - Bus {u.get('bus')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("report_form"):
            cat = st.selectbox("Sistema", ["Motor", "Frenos", "Transmisión", "Llantas", "Suspensión", "Luces", "Otro"])
            desc = st.text_area("Descripción de lo ocurrido o del arreglo")
            cost = st.number_input("Costo aproximado ($)", min_value=0.0)
            mec_sel = st.selectbox("¿Quién lo atendió?", ["No asignado"] + mecs)
            foto = st.camera_input("Foto de evidencia")
            
            if st.form_submit_button("🚀 Enviar Reporte"):
                with st.spinner("Sincronizando con la nube..."):
                    img_b64 = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus'),
                        'category': cat, 'description': desc, 'cost': cost,
                        'mechanic': mec_sel, 'driver': u['name'], 'image': img_b64,
                        'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("¡Reporte guardado con éxito!")

    # --- LÓGICA: IA ---
    elif menu == "🧠 Auditoría IA":
        st.header("Auditoría Inteligente Gemini")
        logs = [d.to_dict() for d in get_ref("maintenance_logs").stream() if d.to_dict().get('fleetId') == u['fleet']]
        stock = [d.to_dict() for d in get_ref("inventory").stream() if d.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            if st.button("🪄 Ejecutar Auditoría"):
                summary = f"Logs: {str(logs)[:2000]} | Stock: {str(stock)}"
                with st.spinner("Analizando patrones de gasto..."):
                    result = call_gemini(summary)
                    st.markdown(f"<div class='ai-box'><h3>Análisis de Gemini</h3>{result}</div>", unsafe_allow_html=True)
        else:
            st.warning("No hay suficientes reportes para que la IA trabaje.")

    # --- LÓGICA: HISTORIAL ---
    elif "Historial" in menu or "Mis Reportes" in menu:
        st.header("Carpeta de Reportes")
        logs = [d.to_dict() for d in get_ref("maintenance_logs").stream() if d.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df_logs = pd.DataFrame(logs).sort_values(by='createdAt', ascending=False)
            for _, row in df_logs.iterrows():
                with st.expander(f"📅 {row['date']} - {row['category']} - Bus {row['busNumber']}"):
                    st.write(f"**Mecánico:** {row.get('mechanic')}")
                    st.write(f"**Trabajo:** {row['description']}")
                    st.write(f"**Costo:** ${row['cost']:,.2f}")
                    if row.get('image'):
                        st.image(base64.b64decode(row['image']), width=350)
        else:
            st.info("No hay registros históricos.")

st.caption(f"AutoGuard Ultimate V1.5 | Enterprise Solutions | ID: {app_id}")
