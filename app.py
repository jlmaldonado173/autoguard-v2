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
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Itero Titanium Pro", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# Semáforo de Colores Oficial
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo/Naranja
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Carrocería": "#ec4899",   # Rosado
    "Otro": "#64748b"          # Gris
}

# --- 2. DISEÑO CSS PREMIUM (MODO ELITE) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f1f5f9; }}
    
    .top-bar {{
        background: #0f172a; color: white; padding: 15px 25px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }}
    .main-content {{ margin-top: 90px; }}
    
    .card {{
        background: white; padding: 25px; border-radius: 30px;
        border: 1px solid #e2e8f0; margin-bottom: 20px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
    }}
    
    .stButton>button {{
        border-radius: 20px; height: 3.8rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 1px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    
    .wa-btn {{
        background-color: #22c55e !important; color: white !important;
        border-radius: 15px !important; text-decoration: none;
        display: flex; align-items: center; justify-content: center;
        padding: 12px; font-weight: 800; border: none;
        box-shadow: 0 4px 6px rgba(34, 197, 94, 0.3);
    }}
    
    .badge {{
        padding: 5px 12px; border-radius: 12px; font-size: 11px;
        font-weight: 800; color: white; text-transform: uppercase;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES TÉCNICAS (LOGO, IA, FIREBASE) ---

def get_logo_img(w=200):
    try:
        # Usamos el nuevo archivo que subiste
        img = Image.open("Gemini_Generated_Image_buyjdmbuyjdmbuyj.png")
        return img
    except: return None

def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((600, 600))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def clean_tel(t):
    c = "".join(filter(str.isdigit, str(t)))
    if len(c) == 10 and c.startswith("0"): return "593" + c[1:]
    return c

def call_gemini_ai(prompt):
    api_key = "" # Inyectado automáticamente
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": "Eres Itero AI Master. Analiza deudas, gastos y eficiencia de buses en Ecuador. Sé directo y busca el ahorro."}]}
    }
    try:
        res = requests.post(url, json=payload, timeout=12)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "IA temporalmente fuera de línea."

# --- 4. FIREBASE (REGLAS 1, 2, 3) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except: return None
    return firestore.client()

db = init_db()
app_id = "itero-titanium-v15"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. PERSISTENCIA DE SESIÓN ---
def session_manager():
    if 'user' not in st.session_state:
        if "session" in st.query_params:
            try: st.session_state.user = json.loads(st.query_params["session"])
            except: st.session_state.user = None
        else: st.session_state.user = None
    
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_titanium_v15');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

session_manager()
if 'page' not in st.session_state: st.session_state.page = "🏠 Dashboard"

# --- 6. PANTALLA DE ACCESO ---
if st.session_state.user is None:
    st.markdown("<div style='text-align:center; padding-top:40px;'>", unsafe_allow_html=True)
    logo_img = get_logo_img()
    if logo_img: st.image(logo_img, width=220)
    else: st.title("🔄 ITERO PRO")
    st.markdown("<h1>Itero Titanium</h1><p>Control Total de Flotas</p></div>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("l_driver"):
            f_id = st.text_input("ID Flota"); u_n = st.text_input("Nombre Conductor"); u_b = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR TURNO"):
                u = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = u
                components.html(f"<script>window.localStorage.setItem('itero_titanium_v15', '{json.dumps(u)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(u)}');</script>", height=0)
                st.rerun()
    with t2:
        with st.form("l_owner"):
            f_o = st.text_input("ID Flota"); o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("MODO ADMINISTRADOR"):
                u = {'role':'owner', 'fleet':f_o.upper().strip(), 'name':o_n}
                st.session_state.user = u
                components.html(f"<script>window.localStorage.setItem('itero_titanium_v15', '{json.dumps(u)}'); window.parent.location.search = '?session=' + encodeURIComponent('{json.dumps(u)}');</script>", height=0)
                st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        logo_s = get_logo_img()
        if logo_s: st.image(logo_s, width=120)
        st.title("Menu")
        menu = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "⛽ Combustible", "👨‍🔧 Mecánicos", "🏢 Almacenes", "📋 Historial y Deudas", "📊 Comparativa", "🤖 Auditor IA"]
        if u['role'] == 'driver': menu = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "⛽ Combustible", "📋 Mis Reportes"]
        
        sel = st.radio("Navegación", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
        
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_titanium_v15'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- PÁGINAS ---

    if st.session_state.page == "🏠 Dashboard":
        st.header("📊 Resumen Operativo")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            for c in ['mec_cost', 'mec_paid', 'sup_cost', 'sup_paid', 'bus']:
                if c not in df.columns: df[c] = 0.0 if 'cost' in c or 'paid' in c else "S/N"
            
            df['total_cost'] = df['mec_cost'] + df['sup_cost']
            df['total_paid'] = df['mec_paid'] + df['sup_paid']
            df['deuda'] = df['total_cost'] - df['total_paid']
            if u['role'] == 'driver': df = df[df['bus'] == u['bus']]

            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Flota", f"${df['total_cost'].sum():,.2f}")
            c2.metric("Deuda Pendiente", f"${df['deuda'].sum():,.2f}", delta_color="inverse")
            c3.metric("U. Monitoreadas", len(df['bus'].unique()))

            st.subheader("🚛 Salud por Unidad")
            buses = sorted(df['bus'].unique())
            cols = st.columns(2)
            for i, bus in enumerate(buses):
                b_df = df[df['bus'] == bus]
                with cols[i % 2]:
                    st.markdown(f"<div class='card'><h3>Bus {bus}</h3><p>Gasto: ${b_df['total_cost'].sum():,.2f}<br>Deuda: ${b_df['deuda'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else: st.info("Itero listo. Esperando primer reporte.")

    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.subheader(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        sups = [s.to_dict()['name'] for s in get_ref("suppliers").stream() if s.to_dict().get('fleetId') == u['fleet']]

        with st.form("f_report_v15", clear_on_submit=True):
            bus_t = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': bus_t = st.text_input("N° Bus")
            
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            trabajo = st.text_input("¿Qué se arregló?")
            detalles = st.text_area("Notas del arreglo")
            
            st.markdown("#### 👨‍🔧 MANO DE OBRA (Mecánico)")
            cm1, cm2 = st.columns(2)
            m_nom = cm1.selectbox("Elegir Mecánico", ["Ninguno/Externo"] + mecs)
            m_cos = cm1.number_input("Costo Trabajo $", min_value=0.0)
            m_abo = cm2.number_input("Abono hoy al Mecánico $", min_value=0.0)
            
            st.markdown("#### 📦 REPUESTOS (Almacén)")
            cs1, cs2 = st.columns(2)
            s_nom = cs1.selectbox("Elegir Almacén", ["Ninguno/Tienda"] + sups)
            s_cos = cs1.number_input("Costo de Piezas $", min_value=0.0)
            s_abo = cs2.number_input("Abono hoy al Almacén $", min_value=0.0)
            
            st.divider()
            foto = st.camera_input("📸 Foto del Recibo/Trabajo")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE TITANIUM"):
                if (m_cos + s_cos) > 0:
                    img_str = process_img(foto)
                    get_ref("logs").add({
                        'fleetId': u['fleet'], 'bus': bus_t, 'category': cat,
                        'part': trabajo, 'desc': detalles, 'type': 'maintenance',
                        'mec_name': m_nom, 'mec_cost': m_cos, 'mec_paid': m_abo,
                        'sup_name': s_nom, 'sup_cost': s_cos, 'sup_paid': s_abo,
                        'image': img_str, 'createdAt': datetime.now(),
                        'date': datetime.now().strftime("%d/%m/%Y")
                    })
                    st.success("✅ ¡Registrado!"); time.sleep(1); st.rerun()

    elif st.session_state.page == "⛽ Combustible":
        st.header("⛽ Control de Combustible")
        with st.form("f_fuel"):
            bus_f = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': bus_f = st.text_input("N° Bus")
            c1, c2 = st.columns(2)
            gal = c1.number_input("Galones", min_value=0.0)
            cost = c2.number_input("Costo Total $", min_value=0.0)
            km = st.number_input("Kilometraje actual", min_value=0)
            if st.form_submit_button("REGISTRAR CARGA"):
                get_ref("logs").add({
                    'fleetId':u['fleet'], 'bus':bus_f, 'category':'Otro',
                    'part':'Combustible', 'cost':cost, 'abono':cost, 'km':km, 'gal':gal,
                    'type':'fuel', 'date':datetime.now().strftime("%d/%m/%Y"), 'createdAt':datetime.now()
                })
                st.success("⛽ Carga guardada."); st.rerun()

    elif st.session_state.page in ["👨‍🔧 Mecánicos", "🏢 Almacenes"]:
        tipo = "mechanics" if "Mecánicos" in st.session_state.page else "suppliers"
        st.header(f"📇 Directorio de {tipo.capitalize()}")
        with st.expander("➕ Nuevo"):
            with st.form(f"f_{tipo}"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp")
                if st.form_submit_button("Guardar"):
                    get_ref(tipo).add({'fleetId':u['fleet'], 'name':n, 'phone':t}); st.rerun()
        
        items = [d.to_dict() for d in get_ref(tipo).stream() if d.to_dict().get('fleetId') == u['fleet']]
        for i in items: st.markdown(f"<div class='card'><b>{i['name']}</b><br>WA: {i.get('phone')}</div>", unsafe_allow_html=True)

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial y Gestión de Pagos")
        
        t_mecs = {m.to_dict()['name']: m.to_dict().get('phone','') for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']}
        t_sups = {s.to_dict()['name']: s.to_dict().get('phone','') for s in get_ref("suppliers").stream() if s.to_dict().get('fleetId') == u['fleet']}
        
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l['bus'] == u['bus']]

        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            st.markdown(f"<div class='card' style='border-left: 12px solid {color}'><h4>Bus {l['bus']} - {l['part']}</h4><p>{l['date']}</p></div>", unsafe_allow_html=True)
            
            if l.get('type') == 'maintenance':
                with st.expander("💰 Abonar y Notificar"):
                    # MECANICO
                    dm = l.get('mec_cost',0) - l.get('mec_paid',0)
                    st.write(f"👨‍🔧 **Mecánico:** {l.get('mec_name')} | Deuda: **${dm:,.2f}**")
                    if dm > 0 and u['role'] == 'owner':
                        v_m = st.number_input(f"Abonar a Mec.", min_value=0.0, max_value=float(dm), key=f"m_{l['id']}")
                        if st.button("Pagar Mecánico", key=f"bm_{l['id']}"):
                            get_ref("logs").document(l['id']).update({'mec_paid': l['mec_paid'] + v_m}); st.rerun()
                        tel = t_mecs.get(l.get('mec_name'))
                        if tel:
                            msg = f"✅ *PAGO MECÁNICO*\nHola {l['mec_name']}, abono de ${v_m:,.2f} por Bus {l['bus']} ({l['part']}). Saldo: ${dm-v_m:,.2f}."
                            st.markdown(f"<a href='https://wa.me/{clean_tel(tel)}?text={urllib.parse.quote(msg)}' target='_blank' class='wa-btn'>📱 WA MECÁNICO</a>", unsafe_allow_html=True)
                    
                    st.divider()
                    # ALMACEN
                    ds = l.get('sup_cost',0) - l.get('sup_paid',0)
                    st.write(f"🏢 **Almacén:** {l.get('sup_name')} | Deuda: **${ds:,.2f}**")
                    if ds > 0 and u['role'] == 'owner':
                        v_s = st.number_input(f"Abonar a Tienda", min_value=0.0, max_value=float(ds), key=f"s_{l['id']}")
                        if st.button("Pagar Almacén", key=f"bs_{l['id']}"):
                            get_ref("logs").document(l['id']).update({'sup_paid': l['sup_paid'] + v_s}); st.rerun()
                        tel_s = t_sups.get(l.get('sup_name'))
                        if tel_s:
                            msg_s = f"✅ *PAGO REPUESTOS*\nHola {l['sup_name']}, abono de ${v_s:,.2f} por Bus {l['bus']} ({l['part']}). Saldo: ${ds-v_s:,.2f}."
                            st.markdown(f"<a href='https://wa.me/{clean_tel(tel_s)}?text={urllib.parse.quote(msg_s)}' target='_blank' class='wa-btn'>📱 WA TIENDA</a>", unsafe_allow_html=True)
                
            if l.get('image'):
                with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)

    elif st.session_state.page == "📊 Comparativa":
        st.header("📊 Inteligencia de Precios")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            st.subheader("🔍 Compara Repuestos")
            rep_sel = st.selectbox("Repuesto:", sorted(df['part'].unique()))
            res = df[df['part'] == rep_sel].groupby('sup_name')['sup_cost'].agg(['min', 'mean', 'count']).reset_index()
            st.table(res.rename(columns={'sup_name':'Almacén', 'min':'Precio Mín', 'mean':'Promedio'}))

    elif st.session_state.page == "🤖 Auditor IA":
        st.header("🤖 Auditoría con Gemini")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            if st.button("🤖 ANALIZAR TODA LA FLOTA"):
                df_ai = pd.DataFrame(logs)[['bus', 'category', 'part', 'mec_cost', 'sup_cost']]
                prompt = f"Analiza estos gastos de buses: {df_ai.to_string()}. Dame 3 consejos de ahorro."
                with st.spinner("IA de Itero analizando..."):
                    st.write(call_gemini_ai(prompt))

st.caption(f"Itero V15.0 Titanium | Smart Care | ID: {app_id}")

