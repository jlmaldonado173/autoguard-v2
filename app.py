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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itero AI", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4", "Otro": "#64748b"
}

# --- 2. ESTILOS APK PREMIUM ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f1f5f9; }}
    
    .top-bar {{
        background: #1e293b; color: white; padding: 15px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .content-area {{ margin-top: 85px; }}
    
    .bus-card {{
        background: white; padding: 20px; border-radius: 24px;
        border-top: 6px solid #3b82f6; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        transition: transform 0.2s;
    }}
    .bus-card:active {{ transform: scale(0.98); }}
    
    .ai-box {{
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        color: white; padding: 20px; border-radius: 20px;
        border-left: 5px solid #3b82f6; margin: 15px 0;
    }}
    
    .stButton>button {{
        border-radius: 16px; height: 3.8rem; font-weight: 700;
        text-transform: uppercase; transition: all 0.3s;
    }}
    
    .wa-button {{
        background-color: #25d366 !important; color: white !important;
        font-weight: 800 !important; border-radius: 12px !important;
        text-decoration: none; display: flex; align-items: center; justify-content: center;
        padding: 12px; margin-top: 10px; border: 1px solid #128c7e;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES TÉCNICAS (IMAGEN, WHATSAPP E IA) ---
def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((500, 500))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def clean_phone(phone):
    clean = "".join(filter(str.isdigit, str(phone)))
    if len(clean) == 10 and clean.startswith("0"): return "593" + clean[1:]
    return clean if len(clean) > 8 else ""

def call_gemini_ai(prompt):
    """Llamada a Gemini 2.5 Flash con Exponential Backoff"""
    api_key = "" # El entorno inyecta la clave automáticamente
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": "Eres un experto mecánico y auditor de flotas de buses en Ecuador. Analiza los gastos y da consejos cortos y claros de ahorro."}]}
    }
    
    for i in range(5):
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
        except:
            time.sleep(2**i)
    return "No pude analizar los datos en este momento. Inténtalo de nuevo."

# --- 4. FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            else:
                cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
        except: return None
    return firestore.client()

db = init_firebase()
app_id = "itero-v8-prod" # Usamos un ID limpio para esta versión

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. SESIÓN Y NAVEGACIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"
if 'selected_bus' not in st.session_state: st.session_state.selected_bus = None

# --- 6. ACCESO (LOGIN) ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#1e293b;'>🛡️ Itero AI V8.0</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("l_d"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                st.session_state.user = {'role':'driver', 'fleet':f_id.upper(), 'name':u_n, 'bus':u_b}; st.rerun()
    with t2:
        with st.form("l_o"):
            f_o = st.text_input("Código de Flota")
            o_n = st.text_input("Dueño")
            if st.form_submit_button("Acceso Total"):
                st.session_state.user = {'role':'owner', 'fleet':f_o.upper(), 'name':o_n}; st.rerun()

# --- 7. APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ Itero AI</span><span>👤 {u['name']}</span></div><div class='content-area'></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("Itero Pro")
        menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial por Bus", "👨‍🔧 Cuentas Mecánicos"]
        if u['role'] == 'driver': menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Ir a:", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.session_state.selected_bus = None; st.rerun()
        
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.user = None; st.rerun()

    # --- PÁGINA: INICIO (DASHBOARD) ---
    if st.session_state.page == "🏠 Inicio":
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if st.session_state.selected_bus:
            # --- VISTA DETALLADA DEL BUS (LA PESTAÑA QUE PEDISTE) ---
            bus_id = st.session_state.selected_bus
            st.header(f"🚛 Expediente Unidad {bus_id}")
            if st.button("⬅️ VOLVER AL LISTADO"): st.session_state.selected_bus = None; st.rerun()
            
            df_bus = pd.DataFrame([l for l in logs if l.get('busNumber') == bus_id])
            if not df_bus.empty:
                c1, c2 = st.columns(2)
                c1.metric("Inversión en este Bus", f"${df_bus['cost'].sum():,.2f}")
                c2.metric("Reportes", len(df_bus))
                
                # --- BOTÓN DE IA ---
                st.markdown("<div class='ai-box'>", unsafe_allow_html=True)
                st.subheader("🧠 Auditoría con IA")
                if st.button("🤖 ANALIZAR ESTADO DEL BUS"):
                    resumen_data = df_bus[['category', 'part_name', 'cost', 'date']].to_string()
                    prompt = f"Analiza estos gastos del bus {bus_id}: {resumen_data}. ¿Qué recomendaciones me das para ahorrar dinero?"
                    with st.spinner("La IA está revisando los arreglos..."):
                        analisis = call_gemini_ai(prompt)
                        st.markdown(f"**Análisis de Itero AI:**\n\n{analisis}")
                st.markdown("</div>", unsafe_allow_html=True)
                
                st.write("### Últimos trabajos de esta unidad")
                st.table(df_bus[['date', 'category', 'part_name', 'cost']].sort_index(ascending=False).head(10))
            else:
                st.warning("Este bus no tiene registros aún.")
        
        else:
            # --- VISTA GENERAL ---
            st.header("📊 Resumen de tu Flota")
            if logs:
                df = pd.DataFrame(logs)
                for c in ['cost', 'abono', 'busNumber', 'mechanic']:
                    if c not in df.columns: df[c] = 0.0 if c in ['cost', 'abono'] else "S/N"
                df['deuda'] = df['cost'] - df['abono']
                
                if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
                
                c1, c2 = st.columns(2)
                c1.metric("Inversión Flota", f"${df['cost'].sum():,.2f}")
                c2.metric("Pendiente de Pago", f"${df['deuda'].sum():,.2f}", delta_color="inverse")
                
                st.divider()
                st.subheader("🚛 Pulsa una Unidad para ver detalle e IA")
                buses = sorted(df['busNumber'].unique())
                cols = st.columns(2)
                for i, bus in enumerate(buses):
                    bus_df = df[df['busNumber'] == bus]
                    with cols[i % 2]:
                        st.markdown(f"""
                        <div class='bus-card'>
                            <h3 style='margin:0'>BUS {bus}</h3>
                            <p style='margin:10px 0; color:#64748b;'>Gasto: <b>${bus_df['cost'].sum():,.2f}</b></p>
                            <p style='margin:0; color:#ef4444;'>Deuda: <b>${(bus_df['cost'] - bus_df['abono']).sum():,.2f}</b></p>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"🔎 VER UNIDAD {bus}", key=f"btn_bus_{bus}"):
                            st.session_state.selected_bus = bus
                            st.rerun()
            else:
                st.info("👋 Registra tu primer bus para empezar.")

    # --- PÁGINA: REPORTAR ARREGLO ---
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.subheader(f"🛠️ Nuevo Reporte - Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_reporte"):
            bus_target = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': bus_target = st.text_input("N° de Bus")
            
            cat = st.selectbox("Categoría", list(CAT_COLORS.keys()))
            trabajo = st.text_input("¿Qué pieza se arregló?")
            col1, col2 = st.columns(2)
            total = col1.number_input("Costo Total $", min_value=0.0)
            abono = col2.number_input("Abono hoy $", min_value=0.0)
            
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            foto = st.camera_input("📸 Foto del Arreglo")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if total > 0:
                    img_data = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': bus_target, 'category': cat,
                        'part_name': trabajo, 'cost': total, 'abono': abono,
                        'mechanic': m_sel, 'image': img_data, 'createdAt': datetime.now(),
                        'date': datetime.now().strftime("%d/%m/%Y")
                    })
                    st.success("✅ ¡Reporte guardado con éxito!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    # --- PÁGINA: CUENTAS MECÁNICOS ---
    elif st.session_state.page == "👨‍🔧 Cuentas Mecánicos":
        st.header("👨‍🔧 Pagos y WhatsApp")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        mecs_data = {m.to_dict()['name']: m.to_dict().get('phone', '') for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']}
        
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            mec_sel = st.selectbox("Mecánico:", ["TODOS"] + sorted(list(df['mechanic'].unique())))
            
            if mec_sel != "TODOS":
                logs_mec = [l for l in logs if l.get('mechanic') == mec_sel and (l.get('cost',0) - l.get('abono',0)) > 0]
                for d in logs_mec:
                    deuda_r = d['cost'] - d['abono']
                    st.markdown(f"<div class='bus-card'><b>Bus {d['busNumber']}</b>: {d['part_name']}<br>Saldo: <b style='color:#ef4444'>${deuda_r:,.2f}</b></div>", unsafe_allow_html=True)
                    
                    c1, c2 = st.columns([2, 1])
                    m_pago = c1.number_input(f"Pagar a {d['part_name']}", min_value=0.0, max_value=float(deuda_r), key=f"p_{d['id']}")
                    if c1.button("Confirmar Pago", key=f"b_{d['id']}"):
                        get_ref("maintenance_logs").document(d['id']).update({'abono': d['abono'] + m_pago}); st.rerun()
                    
                    tel = mecs_data.get(mec_sel, "")
                    if tel:
                        tel_wa = clean_phone(tel)
                        msg = f"✅ *PAGO REGISTRADO*\n\nHola {mec_sel}, abono de *${m_pago:,.2f}* por el Bus {d['busNumber']}. Saldo: *${deuda_r - m_pago:,.2f}*."
                        link_wa = f"https://wa.me/{tel_wa}?text={urllib.parse.quote(msg)}"
                        c2.markdown(f"<a href='{link_wa}' target='_blank' class='wa-button'>📱 WHATSAPP</a>", unsafe_allow_html=True)
        else: st.info("Sin registros.")

st.caption(f"Itero AI V8.0 | Inteligencia Artificial Activa | ID: {app_id}")

