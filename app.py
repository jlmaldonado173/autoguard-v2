import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import time
import streamlit.components.v1 as components
import urllib.parse
from PIL import Image
from io import BytesIO

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Itero Pro", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# Colores del Semáforo de Jose
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

# --- 2. DISEÑO CSS APK PREMIUM ---
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
    .main-content {{ margin-top: 85px; }}
    
    .bus-card {{
        background: white; padding: 22px; border-radius: 24px;
        border: 1px solid #e2e8f0; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    
    .wa-button {{
        background-color: #25d366 !important; color: white !important;
        font-weight: 800 !important; border-radius: 14px !important;
        text-decoration: none; display: flex; align-items: center; justify-content: center;
        padding: 12px; margin-top: 10px; border: 1px solid #128c7e;
        text-align: center; font-size: 14px;
    }}
    
    .stButton>button {{
        border-radius: 18px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; width: 100%; transition: all 0.3s;
    }}
    
    .metric-box {{
        background: white; padding: 15px; border-radius: 20px;
        border-bottom: 4px solid #3b82f6; text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES CORE (FIREBASE & TOOLS) ---

def show_logo(width=150, centered=True):
    if centered:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try: st.image("1000110802.png", use_container_width=True)
            except: st.markdown("<h1 style='text-align:center;'>🔄 ITERO</h1>", unsafe_allow_html=True)
    else:
        try: st.image("1000110802.png", width=width)
        except: st.markdown("### 🔄")

def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((500, 500))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def clean_phone(phone):
    clean = "".join(filter(str.isdigit, str(phone)))
    if len(clean) == 10 and clean.startswith("0"): return "593" + clean[1:]
    return clean

def session_persistence():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_v21_master');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            const currentUrl = window.parent.location.origin + window.parent.location.pathname;
            window.parent.location.href = currentUrl + '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

# --- 4. FIREBASE (REGLA 1, 2, 3) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app(credentials.Certificate("firebase_key.json"))
        except: return None
    return firestore.client()

db = init_db()
app_id = "itero-master-v21"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. GESTIÓN DE SESIÓN ---
session_persistence()
if 'user' not in st.session_state:
    if "session" in st.query_params:
        try: st.session_state.user = json.loads(st.query_params["session"])
        except: st.session_state.user = None
    else: st.session_state.user = None

if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"

# --- 6. PANTALLA DE ACCESO (PROTECCIÓN DE FLOTA) ---
if st.session_state.user is None:
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Acceso Validado</h2>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Propietario"])
    
    with t1:
        with st.form("l_driver"):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_n = st.text_input("Tu Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR"):
                if f_id:
                    fleet_doc = get_ref("fleets").document(f_id).get()
                    if fleet_doc.exists:
                        u_data = {'role':'driver', 'fleet':f_id, 'name':u_n, 'bus':u_b}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_v21_master', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()
                    else: st.error("❌ Código de Flota no registrado. Solicítalo al dueño.")
                else: st.error("Ingresa el código.")
    
    with t2:
        with st.form("l_owner"):
            f_o = st.text_input("Código de Flota (Crea o Ingresa)").upper().strip()
            o_n = st.text_input("Nombre del Dueño")
            if st.form_submit_button("GESTIONAR FLOTA"):
                if f_o and o_n:
                    fleet_doc = get_ref("fleets").document(f_o).get()
                    if fleet_doc.exists:
                        if fleet_doc.to_dict().get('owner_name') == o_n:
                            u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                            st.session_state.user = u_data
                            js = json.dumps(u_data)
                            components.html(f"<script>window.localStorage.setItem('itero_v21_master', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                            st.rerun()
                        else: st.error("❌ El código ya pertenece a otro dueño.")
                    else:
                        get_ref("fleets").document(f_o).set({'owner_name': o_n, 'createdAt': datetime.now()})
                        u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_v21_master', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        show_logo(80, False)
        st.title("Menu Pro")
        opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial General", "💰 Contabilidad", "🏢 Casas Comerciales", "👨‍🔧 Mecánicos"]
        if u['role'] == 'driver': opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Secciones:", opts, index=opts.index(st.session_state.page) if st.session_state.page in opts else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
        
        st.divider()
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_v21_master'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- PÁGINA: INICIO (DASHBOARD) ---
    if st.session_state.page == "🏠 Inicio":
        st.header(f"📊 Estado de Flota {u['fleet']}")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown(f"<div class='metric-box'><small>Inversión</small><br><b>${df['cost'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-box'><small>Abonado</small><br><b>${df['abono'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-box' style='border-color:red'><small>DEUDA</small><br><b style='color:red'>${df['deuda'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            
            st.subheader("Saldos por Unidades")
            buses = sorted(df['busNumber'].unique())
            cols = st.columns(2)
            for i, b in enumerate(buses):
                with cols[i % 2]:
                    st.markdown(f"<div class='bus-card'><h4>Unidad {b}</h4><p>Pendiente: ${df[df['busNumber']==b]['deuda'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else: st.info("Bienvenido. Registra arreglos para ver estadísticas.")

    # --- PÁGINA: REPORTAR ARREGLO ---
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Registro de Daño y Arreglo")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("vendors").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_reporte", clear_on_submit=True):
            bus_n = u.get('bus', "")
            if u['role'] == 'owner': bus_n = st.text_input("Número de Unidad")
            
            st.markdown("### 📋 Información del Trabajo")
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            repuesto = st.text_input("Repuesto / Trabajo realizado")
            calidad = st.selectbox("Calidad", ["Original", "Alterno A", "Alterno B", "Reconstruido"])
            falla = st.text_area("Observación / Falla encontrada")
            
            st.markdown("### 💰 Costos y Proveedores")
            c1, c2 = st.columns(2)
            costo = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            
            v_sel = st.selectbox("Casa Comercial (Donde se compró)", ["Compra Directa"] + casas)
            m_sel = st.selectbox("Mecánico Encargado", ["Externo"] + mecs)
            
            foto = st.camera_input("📸 Foto del Arreglo/Factura")
            
            if st.form_submit_button("🚀 GUARDAR Y NOTIFICAR"):
                if costo > 0 and bus_n:
                    img_data = process_img(foto)
                    data = {
                        'fleetId': u['fleet'], 'busNumber': bus_n, 'category': cat,
                        'part': repuesto, 'quality': calidad, 'vendor': v_sel,
                        'fault': falla, 'cost': costo, 'abono': abono,
                        'mechanic': m_sel, 'image': img_data, 'date': datetime.now().strftime("%d/%m/%Y"),
                        'createdAt': datetime.now(), 'reportedBy': u['name']
                    }
                    get_ref("logs").add(data)
                    st.success("✅ Guardado.")
                    
                    # WhatsApp Automático a Casa Comercial
                    if v_sel != "Compra Directa":
                        v_info = next((c.to_dict() for c in get_ref("vendors").stream() if c.to_dict()['name'] == v_sel), None)
                        if v_info and v_info.get('phone'):
                            tel = clean_phone(v_info['phone'])
                            msg = f"🏢 *NUEVA COMPRA - ITERO*\n\n" \
                                  f"🚛 *Unidad:* {bus_n}\n" \
                                  f"📦 *Pieza:* {repuesto} ({calidad})\n" \
                                  f"💰 *Costo:* ${costo:,.2f}\n" \
                                  f"💵 *Abono:* ${abono:,.2f}\n" \
                                  f"🚨 *Saldo:* ${costo-abono:,.2f}\n" \
                                  f"📝 *Obs:* {falla}"
                            st.markdown(f"<a href='https://wa.me/{tel}?text={urllib.parse.quote(msg)}' target='_blank' class='wa-button'>📲 ENVIAR WHATSAPP A {v_sel}</a>", unsafe_allow_html=True)
                    time.sleep(2); st.rerun()

    # --- PÁGINA: HISTORIAL GENERAL ---
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial Detallado")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            b_filt = st.selectbox("🚛 Filtrar por Unidad:", ["TODOS"] + sorted(df['busNumber'].unique()))
            
            to_show = [l for l in logs if (b_filt == "TODOS" or l.get('busNumber') == b_filt)]
            if u['role'] == 'driver': to_show = [l for l in to_show if l.get('busNumber') == u['bus']]
            
            for l in sorted(to_show, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
                color = CAT_COLORS.get(l.get('category'), "#64748b")
                st.markdown(f"""
                <div class='bus-card' style='border-left: 10px solid {color}'>
                    <div style='display:flex; justify-content:space-between'>
                        <span style='background:{color}; color:white; padding:3px 12px; border-radius:12px; font-size:10px; font-weight:800;'>{l.get('category')}</span>
                        <span style='color:gray; font-size:12px;'>📅 {l.get('date')}</span>
                    </div>
                    <h4 style='margin:10px 0;'>Unidad {l.get('busNumber')} - {l.get('part')} ({l.get('quality')})</h4>
                    <p style='font-size:13px;'><b>Mecánico:</b> {l.get('mechanic')} | <b>Local:</b> {l.get('vendor')}</p>
                    <p style='font-size:13px;'><b>Obs:</b> {l.get('fault')}</p>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <span style='font-size:18px; font-weight:800;'>${l.get('cost', 0):,.2f}</span>
                        <span style='color:{"#16a34a" if l["cost"]==l["abono"] else "#ef4444"}; font-weight:bold; font-size:12px;'>
                            {"✅ PAGADO" if l["cost"]==l["abono"] else f"🚨 DEBE: ${l['cost']-l['abono']:,.2f}"}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if l.get('image'):
                    with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)
        else: st.info("No hay historial.")

    # --- PÁGINA: CONTABILIDAD ---
    elif st.session_state.page == "💰 Contabilidad":
        st.header("💰 Estado de Cuentas")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            
            t1, t2 = st.tabs(["Mecánicos", "Casas Comerciales"])
            with t1:
                st.subheader("Saldos Pendientes con Talleres")
                mec_deudas = df[df['deuda'] > 0].groupby('mechanic')['deuda'].sum().reset_index()
                st.table(mec_deudas)
            with t2:
                st.subheader("Saldos Pendientes con Locales")
                ven_deudas = df[df['deuda'] > 0].groupby('vendor')['deuda'].sum().reset_index()
                st.table(ven_deudas)
        else: st.info("Sin registros contables.")

    # --- PÁGINA: CASAS COMERCIALES ---
    elif st.session_state.page == "🏢 Casas Comerciales":
        st.header("🏢 Casas Comerciales")
        if u['role'] == 'owner':
            with st.expander("➕ REGISTRAR LOCAL"):
                with st.form("f_ven"):
                    vn = st.text_input("Nombre"); vt = st.text_input("WhatsApp"); vd = st.text_input("Dirección")
                    vo = st.text_area("Observación")
                    if st.form_submit_button("Guardar"):
                        get_ref("vendors").add({'fleetId':u['fleet'], 'name':vn, 'phone':vt, 'address':vd, 'obs':vo})
                        st.rerun()
        
        vendors = [v.to_dict() for v in get_ref("vendors").stream() if v.to_dict().get('fleetId') == u['fleet']]
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        for v in vendors:
            v_deuda = sum((l['cost']-l['abono']) for l in logs if l.get('vendor') == v['name'])
            with st.container():
                st.markdown(f"<div class='bus-card'><h3>🏢 {v['name']}</h3><p>📍 {v.get('address')} | 📞 {v.get('phone')}</p><b>Deuda: ${v_deuda:,.2f}</b></div>", unsafe_allow_html=True)
                if v_deuda > 0 and u['role'] == 'owner':
                    with st.expander("Abonar a este local"):
                        for l in [lx for lx in logs if lx.get('vendor') == v['name'] and (lx['cost']-lx['abono']) > 0]:
                            st.write(f"Bus {l['busNumber']} - {l['part']}")
                            amt = st.number_input(f"Monto para {l['id'][:4]}", min_value=0.0, max_value=float(l['cost']-l['abono']), key=f"v_ab_{l['id']}")
                            if st.button("PAGAR", key=f"v_btn_{l['id']}"):
                                get_ref("logs").document(l['id']).update({'abono': l['abono'] + amt})
                                st.rerun()

    # --- PÁGINA: MECÁNICOS ---
    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Taller y Mecánicos")
        if u['role'] == 'owner':
            with st.expander("➕ REGISTRAR MECÁNICO"):
                with st.form("f_mec"):
                    mn = st.text_input("Nombre"); mt = st.text_input("WhatsApp"); md = st.text_input("Dirección")
                    if st.form_submit_button("Guardar"):
                        get_ref("mechanics").add({'fleetId':u['fleet'], 'name':mn, 'phone':mt, 'address':md})
                        st.rerun()
        
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        for m in mecs:
            m_deuda = sum((l['cost']-l['abono']) for l in logs if l.get('mechanic') == m['name'])
            with st.container():
                st.markdown(f"<div class='bus-card'><h3>👨‍🔧 {m['name']}</h3><p>📍 {m.get('address')} | 📞 {m.get('phone')}</p><b>Deuda Total: ${m_deuda:,.2f}</b></div>", unsafe_allow_html=True)
                if m_deuda > 0 and u['role'] == 'owner':
                    with st.expander("Realizar Abono"):
                        for l in [lx for lx in logs if lx.get('mechanic') == m['name'] and (lx['cost']-lx['abono']) > 0]:
                            st.write(f"Bus {l['busNumber']} - {l['part']}")
                            amt = st.number_input(f"Monto {l['id'][:4]}", min_value=0.0, max_value=float(l['cost']-l['abono']), key=f"m_ab_{l['id']}")
                            if st.button("ABONAR", key=f"m_btn_{l['id']}"):
                                get_ref("logs").document(l['id']).update({'abono': l['abono'] + amt})
                                tel_m = clean_phone(m['phone'])
                                msg_m = f"✅ *PAGO REGISTRADO - ITERO*\n\n" \
                                        f"Hola {m['name']}, abono de *${amt:,.2f}* por el Bus {l['busNumber']}.\n" \
                                        f"🔧 *Trabajo:* {l['part']}\n" \
                                        f"🚨 *Saldo:* ${ (l['cost']-l['abono']) - amt :,.2f}"
                                st.markdown(f"<a href='https://wa.me/{tel_m}?text={urllib.parse.quote(msg_m)}' target='_blank' class='wa-button'>📲 ENVIAR COMPROBANTE</a>", unsafe_allow_html=True)
                                time.sleep(1); st.rerun()

st.caption(f"Itero V21.0 | Sistema Centralizado | ID: {app_id}")
