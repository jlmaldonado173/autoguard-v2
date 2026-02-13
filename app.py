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

# --- 2. LOGO EN BASE64 (REPRESENTACIÓN DEL LOGO SUBIDO) ---
# Nota: Jose, aquí puedes reemplazar este string por el Base64 real de tu imagen 
# para que aparezca exactamente la que me pasaste.
LOGO_SVG = """
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="45" fill="none" stroke="#1e293b" stroke-width="2" stroke-dasharray="5,5"/>
    <path d="M30 50 L70 50 M50 30 L50 70" stroke="#3b82f6" stroke-width="8" stroke-linecap="round"/>
    <circle cx="50" cy="50" r="15" fill="#1e293b"/>
    <path d="M40 50 Q50 40 60 50 T80 50" fill="none" stroke="white" stroke-width="3"/>
</svg>
"""

# --- 3. ESTILOS CSS PREMIUM ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .top-bar {{
        background: #1e293b; color: white; padding: 10px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .content-area {{ margin-top: 80px; }}
    
    .bus-card {{
        background: white; padding: 20px; border-radius: 24px;
        border-top: 6px solid #3b82f6; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; transition: all 0.3s;
    }}
    
    .wa-button {{
        background-color: #25d366 !important; color: white !important;
        font-weight: 800 !important; border-radius: 12px !important;
        text-decoration: none; display: flex; align-items: center; justify-content: center;
        padding: 12px; margin-top: 10px; border: 1px solid #128c7e;
    }}
    
    .logo-container {{ text-align: center; padding: 20px; }}
    .logo-img {{ width: 150px; margin-bottom: 10px; }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. FUNCIONES TÉCNICAS ---
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
    api_key = "" # Inyectado automáticamente
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": "Experto mecánico y auditor de buses en Ecuador. Da consejos cortos de ahorro."}]}
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "No pude analizar los datos ahora."

# --- 5. FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except: return None
    return firestore.client()

db = init_firebase()
app_id = "itero-v9-prod"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 6. SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

# --- 7. ACCESO (LOGIN CON LOGO) ---
if st.session_state.user is None:
    st.markdown("<div class='logo-container'>", unsafe_allow_html=True)
    # Aquí mostramos un logo SVG elegante mientras el usuario sube el suyo
    st.markdown(f"<div style='width:120px; margin:auto;'>{LOGO_SVG}</div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center; margin-top:10px;'>Itero</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;'>Smart Vehicle Care</p></div>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("l_d"):
            f_id = st.text_input("Flota"); u_n = st.text_input("Nombre"); u_b = st.text_input("Bus")
            if st.form_submit_button("INGRESAR"):
                st.session_state.user = {'role':'driver', 'fleet':f_id.upper(), 'name':u_n, 'bus':u_b}; st.rerun()
    with t2:
        with st.form("l_o"):
            f_o = st.text_input("Flota"); o_n = st.text_input("Dueño")
            if st.form_submit_button("ACCESO TOTAL"):
                st.session_state.user = {'role':'owner', 'fleet':f_o.upper(), 'name':o_n}; st.rerun()

# --- 8. APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ Itero Pro</span><span>👤 {u['name']}</span></div><div class='content-area'></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(f"<div style='width:80px; margin:auto;'>{LOGO_SVG}</div>", unsafe_allow_html=True)
        st.title("Itero Menu")
        menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial por Bus", "👨‍🔧 Mecánicos (WhatsApp)", "🏢 Casas Comerciales", "🤖 Auditoría IA"]
        if u['role'] == 'driver': menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Navegación:", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
        
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.user = None; st.rerun()

    # --- PÁGINAS ---

    if st.session_state.page == "🏠 Inicio":
        st.header("📊 Resumen de tu Flota")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            for col in ['cost', 'abono', 'busNumber', 'mechanic']:
                if col not in df.columns: df[col] = 0.0 if col in ['cost', 'abono'] else "S/N"
            df['deuda'] = df['cost'] - df['abono']
            
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2 = st.columns(2)
            c1.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Saldo Pendiente", f"${df['deuda'].sum():,.2f}", delta_color="inverse")
            
            st.subheader("🚛 Unidades Registradas")
            buses = sorted(df['busNumber'].unique())
            cols = st.columns(2)
            for i, bus in enumerate(buses):
                bus_df = df[df['busNumber'] == bus]
                with cols[i % 2]:
                    st.markdown(f"<div class='bus-card'><h3>BUS {bus}</h3><p>Gasto: ${bus_df['cost'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else: st.info("No hay reportes registrados.")

    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.subheader(f"🛠️ Registro Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        with st.form("f_report"):
            bus_t = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': bus_t = st.text_input("N° Bus")
            cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló?")
            c1, c2 = st.columns(2)
            total = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            foto = st.camera_input("📸 Evidencia Fotográfica")
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if total > 0:
                    img = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': bus_t, 'category': cat,
                        'part_name': p_name, 'cost': total, 'abono': abono,
                        'mechanic': m_sel, 'image': img, 'createdAt': datetime.now(),
                        'date': datetime.now().strftime("%d/%m/%Y")
                    })
                    st.success("✅ ¡Guardado!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    elif st.session_state.page == "👨‍🔧 Mecánicos (WhatsApp)":
        st.header("👨‍🔧 Cuentas y WhatsApp")
        # Registro
        with st.expander("➕ Registrar Nuevo Mecánico"):
            with st.form("f_mec"):
                m_n = st.text_input("Nombre"); m_t = st.text_input("WhatsApp (Ej: 0987...)")
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t}); st.rerun()
        
        # Pagos
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        mecs_data = {m.to_dict()['name']: m.to_dict().get('phone', '') for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']}
        
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            mec_sel = st.selectbox("Mecánico:", sorted(list(df['mechanic'].unique())))
            
            deudas_m = [l for l in logs if l.get('mechanic') == mec_sel and (l.get('cost',0)-l.get('abono',0)) > 0]
            for d in deudas_m:
                saldo = d['cost'] - d['abono']
                st.markdown(f"<div class='bus-card'><b>Bus {d['busNumber']}</b>: {d['part_name']}<br>Saldo: <b style='color:#ef4444'>${saldo:,.2f}</b></div>", unsafe_allow_html=True)
                
                c1, c2 = st.columns([2,1])
                m_pago = c1.number_input(f"Abonar a {d['part_name']}", min_value=0.0, max_value=float(saldo), key=d['id'])
                if c1.button("Confirmar Pago", key=f"b_{d['id']}"):
                    get_ref("maintenance_logs").document(d['id']).update({'abono': d['abono'] + m_pago}); st.rerun()
                
                tel = mecs_data.get(mec_sel, "")
                if tel:
                    tel_wa = clean_phone(tel)
                    msg = f"✅ *PAGO REGISTRADO*\n\nHola {mec_sel}, abono de *${m_pago:,.2f}* por el Bus {d['busNumber']}. Saldo: *${saldo - m_pago:,.2f}*."
                    link_wa = f"https://wa.me/{tel_wa}?text={urllib.parse.quote(msg)}"
                    c2.markdown(f"<a href='{link_wa}' target='_blank' class='wa-button'>📱 WHATSAPP</a>", unsafe_allow_html=True)

    elif st.session_state.page == "🤖 Auditoría IA":
        st.header("🧠 Inteligencia Artificial")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            if st.button("🤖 ANALIZAR GASTOS DE LA FLOTA"):
                resumen = pd.DataFrame(logs)[['busNumber', 'category', 'part_name', 'cost']].to_string()
                prompt = f"Analiza estos gastos de buses: {resumen}. Dame 3 consejos de ahorro."
                with st.spinner("Itero AI analizando..."):
                    st.write(call_gemini_ai(prompt))

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial de Arreglos")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l['busNumber'] == u['bus']]
        
        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            st.markdown(f"<div class='bus-card' style='border-left: 10px solid {color}'><h4>Bus {l['busNumber']} - {l['part_name']}</h4><p>${l['cost']}</p></div>", unsafe_allow_html=True)
            with st.expander("Ver Detalles"):
                if l.get('image'): st.image(base64.b64decode(l['image']), use_container_width=True)

st.caption(f"Itero V9.0 | Edición de Marca | Smart Vehicle Care | ID: {app_id}")

