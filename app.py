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

# --- 1. CONFIGURACIÓN Y COLORES ---
st.set_page_config(page_title="AutoGuard Elite V2.5", layout="wide", page_icon="🚌", initial_sidebar_state="expanded")

CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- 2. ESTILOS CSS PROFESIONALES ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .card {{ background: white; padding: 20px; border-radius: 16px; border: 1px solid #e2e8f0; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .section-tag {{ padding: 4px 12px; border-radius: 20px; color: white; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
    {" ".join([f".tag-{k} {{ background-color: {v}; }}" for k, v in CAT_COLORS.items()])}
    
    .status-badge {{ padding: 3px 10px; border-radius: 8px; font-size: 12px; font-weight: bold; }}
    .pending {{ background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    
    .navbar {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 12px 20px; border-radius: 12px; color: white; margin-bottom: 20px; }}
    .ai-box {{ background: #eff6ff; border: 1px solid #3b82f6; padding: 20px; border-radius: 12px; color: #1e3a8a; }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO (IMAGEN Y PERSISTENCIA) ---
def process_img(file):
    if file is None: return None
    img = Image.open(file)
    img.thumbnail((500, 500))
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=75)
    return base64.b64encode(buffered.getvalue()).decode()

def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v25_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v25_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v25_session'); window.parent.location.search = '';</script>", height=0)

# --- 4. FIREBASE Y IA ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app(credentials.Certificate("firebase_key.json"))
        except: return None
    return firestore.client()

db = init_firebase()
app_id = "auto-guard-v2-prod"
apiKey = "" # Gemini

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

def call_gemini(data_summary):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    payload = {"contents": [{"parts": [{"text": f"Analiza estos gastos de flota y dame consejos de ahorro: {data_summary}"}]}]}
    try:
        res = requests.post(url, json=payload)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "IA temporalmente no disponible."

# --- 5. MANEJO DE SESIÓN ---
u = st.session_state.get('user', None)
if u is None and "session" in st.query_params:
    try:
        u = json.loads(st.query_params["session"])
        st.session_state.user = u
    except: pass
if u is None: session_persistence_js()

# --- 6. VISTA: ACCESO ---
if u is None:
    st.markdown("<h1 style='text-align:center;'>🛡️ AutoGuard Elite V2.5</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administradores"])
    with t1:
        with st.form("d_login"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Tu Nombre")
            u_b = st.text_input("N° de Bus")
            if st.form_submit_button("Ingresar"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("o_login"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Nombre Administrador")
            if st.form_submit_button("Acceso Total"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- 7. VISTA: APLICACIÓN ---
else:
    st.markdown(f"<div class='navbar'><span>👤 {u['name']} | <b>{u['fleet']}</b></span><span>V2.5 ULTIMATE</span></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("Menú Principal")
        if u['role'] == 'owner':
            options = ["🏠 Dashboard", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "📦 Repuestos", "🛠️ Reportar Daño", "📋 Historial y Pagos", "🧠 Auditoría IA"]
        else:
            options = ["🏠 Mi Estado", "🛠️ Reportar Daño", "📋 Mis Reportes"]
        
        menu_opt = st.radio("Navegación", options)
        st.divider()
        if st.sidebar.button("🚪 Cerrar Sesión", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- LÓGICA DE CONTENIDO ---
    
    # --- DASHBOARD ---
    if "Dashboard" in menu_opt or "Mi Estado" in menu_opt:
        st.header("📈 Resumen de Operación")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            for col in ['paid', 'cost', 'category', 'next_change_date']:
                if col not in df.columns: df[col] = False if col == 'paid' else (0 if col == 'cost' else "")
            
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente", f"${df[df['paid']==False]['cost'].sum():,.2f}")
            c3.metric("Reportes", len(df))
            
            st.subheader("Gastos por Sección (Colores)")
            st.bar_chart(df.groupby('category')['cost'].sum())
        else: st.info("Bienvenido. Registra el primer arreglo para ver datos.")

    # --- MECÁNICOS ---
    elif menu_opt == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Gestión de Mecánicos")
        with st.expander("🆕 Registrar Mecánico"):
            with st.form("f_mec"):
                m_n = st.text_input("Nombre"); m_t = st.text_input("Teléfono"); m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                    st.success("Registrado"); st.rerun()
        
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in mecs: st.write(f"**{m['name']}** - 📞 {m['phone']} ({m['specialty']})")

    # --- CASAS COMERCIALES ---
    elif menu_opt == "🏢 Casas Comerciales":
        st.header("🏢 Comparación de Casas Comerciales")
        with st.expander("➕ Registrar Casa Comercial"):
            with st.form("f_casa"):
                c_n = st.text_input("Nombre Negocio"); c_t = st.text_input("Contacto")
                if st.form_submit_button("Guardar"):
                    get_ref("suppliers").add({'fleetId':u['fleet'], 'name':c_n, 'phone':c_t})
                    st.success("Guardado"); st.rerun()
        
        # Comparativa de precios
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if 'part_name' in df.columns:
                rep = st.selectbox("Compara precios de:", df['part_name'].unique())
                st.table(df[df['part_name'] == rep].groupby('supplier')['cost'].min().reset_index())

    # --- REPUESTOS ---
    elif menu_opt == "📦 Repuestos":
        st.header("📦 Inventario de Repuestos")
        with st.form("f_inv"):
            it = st.text_input("Repuesto"); qt = st.number_input("Cantidad", min_value=0); mn = st.number_input("Mínimo", min_value=1)
            if st.form_submit_button("Agregar"):
                get_ref("inventory").add({'fleetId':u['fleet'], 'item':it, 'quantity':qt, 'min_stock':mn})
                st.success("Inventario actualizado"); st.rerun()

    # --- REPORTAR DAÑO (CON FOTO) ---
    elif menu_opt == "🛠️ Reportar Daño":
        st.header(f"🛠️ Reporte Detallado - Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep_ultimate"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
                p_name = st.text_input("¿Qué se arregló? (Ej: Cambio de rodillos)")
                det = st.text_area("Detalle (Ej: Sin frenos, ruidos)")
            with col2:
                cost = st.number_input("Costo Total $", min_value=0.0)
                paid = st.checkbox("¿Ya está pagado?")
                next_d = st.date_input("Próximo cambio programado", value=None)
            
            foto = st.camera_input("📸 Toma una foto del arreglo/factura")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            
            if st.form_submit_button("🚀 ENVIAR REPORTE COMPLETO"):
                with st.spinner("Subiendo evidencia..."):
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                        'category': cat, 'part_name': p_name, 'description': det,
                        'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                        'image': img_data, 'next_change_date': str(next_d) if next_d else "",
                        'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Guardado con éxito!"); time.sleep(1); st.rerun()

    # --- HISTORIAL ---
    elif "Historial" in menu_opt or "Reportes" in menu_opt:
        st.header("📋 Historial, Fotos y Pagos")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span class='section-tag tag-{l['category']}'>{l['category']}</span>
                    <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "PENDIENTE"}</span>
                </div>
                <h4 style='margin-top:10px'>{l.get('part_name')} - Bus {l.get('busNumber')}</h4>
                <p><b>Detalle:</b> {l.get('description', 'S/D')}</p>
                <p><b>Costo:</b> ${l['cost']:,.2f} | <b>Mecánico:</b> {l.get('mechanic')}</p>
            </div>
            """, unsafe_allow_html=True)
            if l.get('image'):
                with st.expander("🖼️ Ver Foto"): st.image(base64.b64decode(l['image']), use_container_width=True)
            if not l.get('paid') and u['role'] == 'owner':
                if st.button(f"Saldar Pago {l['id'][:4]}", key=l['id']):
                    get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

    # --- AUDITORÍA IA ---
    elif menu_opt == "🧠 Auditoría IA":
        st.header("🧠 Auditoría Gemini")
        if st.button("🪄 Ejecutar Análisis"):
            st.info("La IA está analizando tus gastos..."); time.sleep(1)
            # Aquí iría la llamada real a call_gemini

st.caption(f"AutoGuard Elite V2.5 | Gestión Total Sin Eliminaciones | ID: {app_id}")

