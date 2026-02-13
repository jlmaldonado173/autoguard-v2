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

# Semáforo de Colores (Estricto pedido de Jose)
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

# --- 2. DISEÑO CSS PREMIUM (ESTILO APK) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .top-bar {{
        background: #1e293b; color: white; padding: 12px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
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
    
    .metric-card {{
        background: #ffffff; padding: 15px; border-radius: 20px;
        border-bottom: 4px solid #3b82f6; text-align: center;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES CORE ---

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
        const stored = window.localStorage.getItem('itero_master_session');
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (stored && !urlParams.has('session')) {
            const currentUrl = window.parent.location.origin + window.parent.location.pathname;
            window.parent.location.href = currentUrl + '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

# --- 4. FIREBASE ---
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
app_id = "itero-master-v19"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. GESTIÓN DE SESIÓN ---
session_persistence()
if 'user' not in st.session_state:
    if "session" in st.query_params:
        try: st.session_state.user = json.loads(st.query_params["session"])
        except: st.session_state.user = None
    else: st.session_state.user = None

if 'page' not in st.session_state: st.session_state.page = "🏠 Dashboard"

# --- 6. PANTALLA DE ACCESO (VALIDADA) ---
if st.session_state.user is None:
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Acceso Validado</h2>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Propietario"])
    
    with t1:
        with st.form("l_driver"):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("INGRESAR"):
                if f_id:
                    fleet_doc = get_ref("fleets").document(f_id).get()
                    if fleet_doc.exists:
                        u_data = {'role':'driver', 'fleet':f_id, 'name':u_n, 'bus':u_b}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_master_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()
                    else: st.error("❌ Código de Flota no registrado.")
                else: st.error("Ingresa un código.")
                
    with t2:
        with st.form("l_owner"):
            f_o = st.text_input("Código de Flota").upper().strip()
            o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("GESTIONAR"):
                if f_o and o_n:
                    fleet_doc = get_ref("fleets").document(f_o).get()
                    if fleet_doc.exists:
                        if fleet_doc.to_dict().get('owner_name') == o_n:
                            u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                            st.session_state.user = u_data
                            js = json.dumps(u_data)
                            components.html(f"<script>window.localStorage.setItem('itero_master_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                            st.rerun()
                        else: st.error("❌ Este código ya pertenece a otro dueño.")
                    else:
                        get_ref("fleets").document(f_o).set({'owner_name': o_n, 'createdAt': datetime.now()})
                        u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_master_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()

# --- 7. APLICACIÓN PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        show_logo(80, False)
        st.title("Panel Itero")
        opts = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Historial General", "💰 Contabilidad", "👨‍🔧 Mecánicos"]
        if u['role'] == 'driver': opts = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Secciones:", opts, index=opts.index(st.session_state.page) if st.session_state.page in opts else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
        
        st.divider()
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_master_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- PÁGINAS ---

    if st.session_state.page == "🏠 Dashboard":
        st.header(f"📊 Estado de Flota {u['fleet']}")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            if u['role'] == 'driver': df = df[df['busNumber'] == u['bus']]
            
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown(f"<div class='metric-card'><small>Inversión</small><br><b>${df['cost'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><small>Abonado</small><br><b>${df['abono'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card' style='border-color:red'><small>DEUDA</small><br><b style='color:red'>${df['deuda'].sum():,.2f}</b></div>", unsafe_allow_html=True)
            
            st.subheader("Saldos por Unidad")
            buses = sorted(df['busNumber'].unique())
            cols = st.columns(2)
            for i, b in enumerate(buses):
                with cols[i % 2]:
                    st.markdown(f"<div class='bus-card'><h4>Bus {b}</h4><p>Deuda: ${df[df['busNumber']==b]['deuda'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else: st.info("Bienvenido. Registra un arreglo para ver estadísticas.")

    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Registro de Mantenimiento")
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        with st.form("f_rep", clear_on_submit=True):
            bus_n = u.get('bus', "")
            if u['role'] == 'owner': bus_n = st.text_input("Número de Bus")
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            repuesto = st.text_input("Repuestos Utilizados / Trabajo")
            obs = st.text_area("Observación / Falla Presentada")
            c1, c2 = st.columns(2)
            total = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            m_sel = st.selectbox("Mecánico Encargado", ["Externo"] + [m['name'] for m in mecs])
            foto = st.camera_input("📸 Foto del Arreglo/Factura")
            
            if st.form_submit_button("🚀 GUARDAR Y NOTIFICAR"):
                if total > 0 and bus_n:
                    img_b64 = process_img(foto)
                    data = {
                        'fleetId': u['fleet'], 'busNumber': bus_n, 'category': cat,
                        'part': repuesto, 'fault': obs, 'cost': total, 'abono': abono,
                        'mechanic': m_sel, 'image': img_b64, 'date': datetime.now().strftime("%d/%m/%Y"),
                        'createdAt': datetime.now(), 'reportedBy': u['name']
                    }
                    get_ref("logs").add(data)
                    st.success("✅ ¡Guardado!")
                    
                    # WhatsApp Automático
                    if m_sel != "Externo":
                        m_data = next((m for m in mecs if m['name'] == m_sel), None)
                        if m_data and m_data.get('phone'):
                            tel = clean_phone(m_data['phone'])
                            msg = f"🛠️ *NUEVO REPORTE - ITERO*\n\n" \
                                  f"🚛 *Bus:* {bus_n}\n" \
                                  f"🔧 *Trabajo:* {repuesto}\n" \
                                  f"📝 *Falla:* {obs}\n" \
                                  f"💰 *Costo:* ${total:,.2f}\n" \
                                  f"💵 *Abono:* ${abono:,.2f}\n" \
                                  f"🚨 *Saldo:* ${total-abono:,.2f}"
                            st.markdown(f"<a href='https://wa.me/{tel}?text={urllib.parse.quote(msg)}' target='_blank' class='wa-button'>📲 NOTIFICAR A MECÁNICO</a>", unsafe_allow_html=True)
                    time.sleep(2); st.rerun()

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial Detallado")
        raw_logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if raw_logs:
            df = pd.DataFrame(raw_logs)
            b_filt = st.selectbox("🚛 Filtrar por Unidad:", ["TODOS"] + sorted(df['busNumber'].unique()))
            
            logs_to_show = [l for l in raw_logs if (b_filt == "TODOS" or l.get('busNumber') == b_filt)]
            if u['role'] == 'driver': logs_to_show = [l for l in logs_to_show if l.get('busNumber') == u['bus']]
            
            for l in sorted(logs_to_show, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
                color = CAT_COLORS.get(l.get('category'), "#64748b")
                st.markdown(f"""
                <div class='bus-card' style='border-left: 10px solid {color}'>
                    <div style='display:flex; justify-content:space-between'>
                        <span style='background:{color}; color:white; padding:3px 12px; border-radius:12px; font-size:10px; font-weight:800;'>{l.get('category')}</span>
                        <span style='color:gray; font-size:12px;'>📅 {l.get('date')}</span>
                    </div>
                    <h4 style='margin:10px 0;'>Unidad {l.get('busNumber')} - {l.get('part')}</h4>
                    <p style='font-size:14px;'><b>Mecánico:</b> {l.get('mechanic')}</p>
                    <p style='font-size:14px;'><b>Obs:</b> {l.get('fault')}</p>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-top:10px;'>
                        <span style='font-weight:800'>${l.get('cost', 0):,.2f}</span>
                        <span style='color:{"#16a34a" if l["cost"]==l["abono"] else "#ef4444"}; font-weight:bold; font-size:12px;'>
                            {"✅ PAGADO" if l["cost"]==l["abono"] else f"🚨 DEBE: ${l['cost']-l['abono']:,.2f}"}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if l.get('image'):
                    with st.expander("🖼️ Ver Evidencia"): st.image(base64.b64decode(l['image']), use_container_width=True)

    elif st.session_state.page == "💰 Contabilidad":
        st.header("💰 Cuentas y Saldos")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            deudas = df[df['deuda'] > 0]
            
            st.subheader("Resumen de Deudas Pendientes")
            if not deudas.empty:
                for _, d in deudas.iterrows():
                    st.markdown(f"<div class='bus-card'><b>Bus {d['busNumber']}</b> | {d['part']}<br>Saldo: <b style='color:red'>${d['deuda']:,.2f}</b></div>", unsafe_allow_html=True)
            else: st.success("🎉 ¡Sin deudas!")

    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Gestión de Mecánicos")
        with st.expander("➕ REGISTRAR MECÁNICO / TALLER"):
            with st.form("f_mec"):
                n = st.text_input("Nombre / Razón Social")
                t = st.text_input("WhatsApp (Ej: 09...)")
                d = st.text_input("Dirección del Taller")
                if st.form_submit_button("GUARDAR"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':n, 'phone':t, 'address':d})
                    st.rerun()
        
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        raw_logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        for m in mecs:
            m_logs = [l for l in raw_logs if l.get('mechanic') == m['name']]
            total_m_deuda = sum((l['cost'] - l['abono']) for l in m_logs)
            
            with st.container():
                st.markdown(f"""
                <div class='bus-card'>
                    <h3>👤 {m['name']}</h3>
                    <p>📞 {m.get('phone')} | 📍 {m.get('address')}</p>
                    <p style='font-size:1.5rem; font-weight:800; color:{"#ef4444" if total_m_deuda > 0 else "#22c55e"};'>
                        Deuda: ${total_m_deuda:,.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                if total_m_deuda > 0:
                    with st.expander("Abonar a este mecánico"):
                        for l in [lx for lx in m_logs if (lx['cost'] - lx['abono']) > 0]:
                            saldo = l['cost'] - l['abono']
                            st.write(f"**Bus {l['busNumber']}**: {l['part']}")
                            c1, c2 = st.columns([2, 1])
                            monto = c1.number_input(f"Monto para {l['id'][:4]}", min_value=0.0, max_value=float(saldo), key=f"ab_{l['id']}")
                            if c2.button("ABONAR", key=f"bt_{l['id']}"):
                                get_ref("logs").document(l['id']).update({'abono': l['abono'] + monto})
                                # WhatsApp Comprobante
                                tel_wa = clean_phone(m['phone'])
                                msg_abono = f"✅ *COMPROBANTE DE PAGO*\n\n" \
                                            f"Hola {m['name']}, abono de *${monto:,.2f}* por el Bus {l['busNumber']}.\n" \
                                            f"Trabajo: {l['part']}\n" \
                                            f"Saldo restante: *${saldo-monto:,.2f}*"
                                st.markdown(f"<a href='https://wa.me/{tel_wa}?text={urllib.parse.quote(msg_abono)}' target='_blank' class='wa-button'>📲 ENVIAR COMPROBANTE</a>", unsafe_allow_html=True)
                                time.sleep(1); st.rerun()

st.caption(f"Itero V19.0 Master | ID: {app_id}")
