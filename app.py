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
st.set_page_config(page_title="Itero Pro", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# Semáforo de Colores por Sección (Tu pedido exacto)
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Carrocería": "#ec4899",   # Rosado
    "Otro": "#64748b"          # Gris
}

# --- 2. DISEÑO APK PREMIUM (CSS) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .top-bar {{
        background: #1e293b; color: white; padding: 12px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .main-container {{ margin-top: 80px; }}
    
    /* Tarjetas de Unidad */
    .bus-card {{
        background: white; padding: 20px; border-radius: 24px;
        border: 1px solid #e2e8f0; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    
    /* Etiquetas de Sección Coloreadas */
    .section-badge {{
        padding: 5px 12px; border-radius: 20px; color: white;
        font-size: 10px; font-weight: 800; text-transform: uppercase;
    }}
    
    /* Botones de Acción */
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; transition: all 0.3s;
    }}
    
    .wa-btn {{
        background-color: #25d366 !important; color: white !important;
        border-radius: 12px !important; text-decoration: none;
        display: flex; align-items: center; justify-content: center;
        padding: 12px; font-weight: bold; border: 1px solid #128c7e;
    }}
    
    .price-low {{ color: #16a34a; font-weight: bold; }}
    .price-high {{ color: #ef4444; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES TÉCNICAS ---
def get_logo():
    try:
        # Intentamos cargar el logo que subiste
        img = Image.open("1000110802.png")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except: return None

def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((600, 600))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def clean_phone(phone):
    clean = "".join(filter(str.isdigit, str(phone)))
    if len(clean) == 10 and clean.startswith("0"): return "593" + clean[1:]
    return clean

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
app_id = "itero-enterprise-v10"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. PERSISTENCIA DE SESIÓN ---
def session_persistence():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_pro_session');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass
if st.session_state.user is None: session_persistence()

# --- 6. LOGIN ---
if st.session_state.user is None:
    logo_b64 = get_logo()
    st.markdown("<div style='text-align:center; padding-top:50px;'>", unsafe_allow_html=True)
    if logo_b64: st.image(f"data:image/png;base64,{logo_b64}", width=150)
    st.markdown("<h1>Itero Pro</h1><p>Smart Vehicle Care</p></div>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Propietarios"])
    with t1:
        with st.form("l_driver"):
            f_id = st.text_input("Código Flota"); u_n = st.text_input("Tu Nombre"); u_b = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR"):
                u = {'role':'driver', 'fleet':f_id.upper(), 'name':u_n, 'bus':u_b}
                st.session_state.user = u
                components.html(f"<script>window.localStorage.setItem('itero_pro_session', '{json.dumps(u)}');</script>", height=0)
                st.rerun()
    with t2:
        with st.form("l_owner"):
            f_o = st.text_input("Código Flota"); o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("ACCESO TOTAL"):
                u = {'role':'owner', 'fleet':f_o.upper(), 'name':o_n}
                st.session_state.user = u
                components.html(f"<script>window.localStorage.setItem('itero_pro_session', '{json.dumps(u)}');</script>", height=0)
                st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ ITERO</span><span>{u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        logo_side = get_logo()
        if logo_side: st.image(f"data:image/png;base64,{logo_side}", width=100)
        st.title("Panel de Control")
        menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial y Pagos", "🏢 Casas Comerciales", "👨‍🔧 Mecánicos", "📦 Repuestos", "🧠 Auditoría IA"]
        if u['role'] == 'driver': menu = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Navegación", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
        
        st.divider()
        if st.button("Cerrar Sesión"):
            components.html("<script>window.localStorage.removeItem('itero_pro_session'); window.parent.location.search = '';</script>", height=0)
            st.session_state.user = None; st.rerun()

    # --- PÁGINA: INICIO (DASHBOARD) ---
    if st.session_state.page == "🏠 Inicio":
        st.header("📊 Dashboard de Flota")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            df = pd.DataFrame(logs)
            for col in ['cost', 'abono', 'bus', 'category', 'date_next']:
                if col not in df.columns: df[col] = 0.0 if col in ['cost', 'abono'] else ""
            df['deuda'] = df['cost'] - df['abono']
            if u['role'] == 'driver': df = df[df['bus'] == u['bus']]

            # Notificaciones de Cambios Posteriores
            alertas = df[df['date_next'] != ""]
            if not alertas.empty:
                st.warning(f"🔔 Tienes {len(alertas)} mantenimientos programados para revisión próxima.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Inversión", f"${df['cost'].sum():,.2f}")
            c2.metric("Abonado", f"${df['abono'].sum():,.2f}")
            c3.metric("DEUDA", f"${df['deuda'].sum():,.2f}", delta_color="inverse")

            # Semáforo de Gastos por Sección
            st.subheader("Semáforo de Gastos (Colores)")
            costos_cat = df.groupby('category')['cost'].sum().reset_index()
            for _, row in costos_cat.iterrows():
                color = CAT_COLORS.get(row['category'], "#64748b")
                st.markdown(f"<div style='display:flex; align-items:center; margin-bottom:5px;'><div style='width:20px; height:20px; background:{color}; border-radius:4px; margin-right:10px;'></div><b>{row['category']}:</b> ${row['cost']:,.2f}</div>", unsafe_allow_html=True)
        else: st.info("👋 Bienvenido a Itero. Comienza reportando un arreglo.")

    # --- PÁGINA: REPORTAR ARREGLO ---
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.subheader(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]

        with st.form("f_report"):
            bus_t = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': bus_t = st.text_input("N° Bus")
            
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            parte = st.text_input("Repuesto/Trabajo (Ej: Cambio de rodillos)")
            det = st.text_area("Detalle (Ej: Sin frenos)")
            
            c1, c2 = st.columns(2)
            total = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            next_m = st.date_input("Próximo cambio programado", value=None)
            foto = st.camera_input("📸 Evidencia Fotográfica")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if total > 0:
                    img_data = process_img(foto)
                    get_ref("logs").add({
                        'fleetId': u['fleet'], 'bus': bus_t, 'category': cat,
                        'part': parte, 'desc': det, 'cost': total, 'abono': abono,
                        'mechanic': m_sel, 'supplier': c_sel, 'image': img_data,
                        'date_next': str(next_m) if next_m else "",
                        'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success("✅ ¡Registrado en Itero!"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    # --- PÁGINA: CASAS COMERCIALES (COMPARATIVA) ---
    elif st.session_state.page == "🏢 Casas Comerciales":
        st.header("🏢 Comparativa de Casas Comerciales")
        with st.expander("➕ Registrar Proveedor"):
            with st.form("f_sup"):
                n = st.text_input("Nombre Negocio"); t = st.text_input("Teléfono")
                if st.form_submit_button("Guardar"):
                    get_ref("suppliers").add({'fleetId':u['fleet'], 'name':n, 'phone':t}); st.rerun()
        
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            st.subheader("💰 ¿Dónde es más barato?")
            part_choice = st.selectbox("Selecciona un repuesto para comparar:", sorted(df['part'].unique()))
            comp_df = df[df['part'] == part_choice].groupby('supplier')['cost'].agg(['min', 'mean', 'count']).reset_index()
            st.table(comp_df.rename(columns={'supplier':'Tienda', 'min':'Precio Mínimo', 'mean':'Precio Promedio', 'count':'Veces Comprado'}))

    # --- PÁGINA: MECÁNICOS (COMPARATIVA Y WHATSAPP) ---
    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Ranking y Pagos a Mecánicos")
        with st.expander("➕ Registrar Especialista"):
            with st.form("f_mec"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); s = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':n, 'phone':t, 'spec':s}); st.rerun()
        
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            st.subheader("🏆 Desempeño por Mecánico")
            st.bar_chart(df.groupby('mechanic')['cost'].sum())
            
            st.subheader("💸 Salda deudas y notifica")
            mec_sel = st.selectbox("Elegir Mecánico:", df['mechanic'].unique())
            mec_phone = next((m.to_dict().get('phone') for m in get_ref("mechanics").stream() if m.to_dict().get('name') == mec_sel), "")
            
            deudas = [l for l in logs if l.get('mechanic') == mec_sel and (l.get('cost',0)-l.get('abono',0)) > 0]
            for d in deudas:
                saldo = d['cost'] - d['abono']
                with st.container():
                    st.markdown(f"<div class='bus-card'><b>Bus {d['bus']}</b>: {d['part']} - Deuda: <span style='color:red'>${saldo:,.2f}</span></div>", unsafe_allow_html=True)
                    m_pago = st.number_input(f"Abonar a {d['id'][:4]}", min_value=0.0, max_value=float(saldo), key=d['id'])
                    if st.button(f"Confirmar Pago {d['id'][:4]}"):
                        get_ref("logs").document(d['id']).update({'abono': d['abono'] + m_pago}); st.rerun()
                    
                    if mec_phone:
                        wa_tel = clean_phone(mec_phone)
                        msg = f"✅ *Itero Pro - Comprobante*\nHola {mec_sel}, abono de ${m_pago:,.2f} por el Bus {d['bus']}. Nuevo saldo: ${saldo - m_pago:,.2f}."
                        st.markdown(f"<a href='https://wa.me/{wa_tel}?text={urllib.parse.quote(msg)}' target='_blank' class='wa-btn'>📱 ENVIAR POR WHATSAPP</a>", unsafe_allow_html=True)

    # --- PÁGINA: HISTORIAL ---
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Carpeta de Mantenimiento")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if u['role'] == 'driver': logs = [l for l in logs if l['bus'] == u['bus']]
        
        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            st.markdown(f"""
            <div class='bus-card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span class='section-badge' style='background:{color}'>{l.get('category')}</span>
                    <span style='font-size:12px; color:#64748b'>{l.get('date')}</span>
                </div>
                <h4 style='margin:10px 0;'>Bus {l.get('bus')} - {l.get('part')}</h4>
                <p style='font-size:14px; color:#1e293b'><b>Detalle:</b> {l.get('desc', 'S/D')}</p>
                <div style='display:flex; justify-content:space-between; align-items:center'>
                    <span style='font-weight:bold; font-size:1.1rem'>${l.get('cost', 0):,.2f}</span>
                    <span style='color:{"#16a34a" if l.get("cost")==l.get("abono") else "#ef4444"}; font-weight:bold'>
                        {"PAGADO" if l.get("cost")==l.get("abono") else f"DEBE: ${l.get('cost',0)-l.get('abono',0):,.2f}"}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if l.get('image'):
                with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)

st.caption(f"Itero V10.0 | Smart Vehicle Care | Organización Total | ID: {app_id}")

