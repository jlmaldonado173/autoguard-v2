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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itero", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4", "Otro": "#64748b"
}

# --- 2. ESTILOS CSS APK PREMIUM ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .top-bar {{
        background: #1e293b; color: white; padding: 15px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .content-area {{ margin-top: 85px; }}
    
    .bus-card {{
        background: white; padding: 20px; border-radius: 20px;
        border-top: 6px solid #3b82f6; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }}
    
    .status-badge {{ padding: 4px 12px; border-radius: 20px; font-size: 10px; font-weight: bold; text-transform: uppercase; }}
    .pending {{ background: #fee2e2; color: #ef4444; }}
    .partial {{ background: #fef3c7; color: #d97706; }}
    .full {{ background: #dcfce7; color: #16a34a; }}
    
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; transition: all 0.3s;
    }}
    .whatsapp-btn {{
        background-color: #25d366 !important;
        color: white !important;
        border: none !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO ---
def process_img(file):
    if file is None: return None
    try:
        img = Image.open(file)
        img.thumbnail((600, 600))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('itero_session_v61', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('itero_session_v61'); window.parent.location.search = '';</script>", height=0)

# --- 4. FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except: return None
    return firestore.client()

db = init_firebase()
app_id = "auto-guard-v2-prod"

def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- 5. LÓGICA DE SESIÓN ---
u = st.session_state.get('user', None)
if u is None and "session" in st.query_params:
    try:
        u = json.loads(st.query_params["session"])
        st.session_state.user = u
    except: pass

# --- 6. PANTALLA DE ACCESO ---
if u is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#1e293b;'>Itero</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;'>Gestión Inteligente de Flotas</p>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Unidad (Bus)")
            if st.form_submit_button("Entrar"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("login_owner"):
            f_o = st.text_input("Código de Flota")
            o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("Acceso Total"):
                user = {'role':'owner', 'fleet':f_o.upper().strip(), 'name':o_n}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- 7. APP PRINCIPAL ---
else:
    # Barra Superior
    st.markdown(f"<div class='top-bar'><span>🛡️ Itero</span><span>👤 {u['name']}</span></div><div class='content-area'></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("Itero Pro")
        menu = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Historial por Bus", "👨‍🔧 Deudas Mecánicos", "🏢 Casas Comerciales", "📦 Repuestos"]
        if u['role'] == 'driver': menu = ["🏠 Dashboard", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        page = st.radio("Menú", menu, index=0)
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- DASHBOARD ---
    if page == "🏠 Dashboard":
        st.header("📊 Finanzas de la Flota")
        logs_raw = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs_raw:
            df = pd.DataFrame(logs_raw)
            for c in ['cost', 'abono', 'busNumber', 'mechanic']:
                if c not in df.columns: df[c] = 0.0 if c in ['cost', 'abono'] else "S/N"
            df['deuda'] = df['cost'] - df['abono']

            if u['role'] == 'driver':
                df = df[df['busNumber'] == u['bus']]
                st.subheader(f"Estado de Unidad: {u['bus']}")
                c1, c2 = st.columns(2)
                c1.metric("Inversión", f"${df['cost'].sum():,.2f}")
                c2.metric("Abonado", f"${df['abono'].sum():,.2f}")
            else:
                st.subheader("🚛 Unidades Registradas")
                buses = sorted(df['busNumber'].unique())
                cols = st.columns(3)
                for i, bus in enumerate(buses):
                    bus_df = df[df['busNumber'] == bus]
                    with cols[i % 3]:
                        st.markdown(f"""
                        <div class='bus-card'>
                            <h3 style='margin:0'>Bus {bus}</h3>
                            <p style='margin:5px 0'>Total: <b>${bus_df['cost'].sum():,.2f}</b></p>
                            <p style='margin:0; color:#ef4444'>Deuda: <b>${bus_df['deuda'].sum():,.2f}</b></p>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.divider()
                st.subheader("👨‍🔧 Deudas con Mecánicos")
                res_mec = df.groupby('mechanic')['deuda'].sum().reset_index()
                for _, row in res_mec.iterrows():
                    if row['deuda'] > 0:
                        st.warning(f"Se debe `${row['deuda']:,.2f}` a **{row['mechanic']}**")
        else:
            st.info("Sin registros.")

    # --- REPORTAR ---
    elif page == "🛠️ Reportar Arreglo":
        st.subheader(f"🛠️ Registro Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]

        with st.form("f_itero"):
            target_bus = u.get('bus', 'ADMIN')
            if u['role'] == 'owner': target_bus = st.text_input("Número de Bus")
            
            cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló/compró?")
            
            c1, c2 = st.columns(2)
            c_total = c1.number_input("Costo TOTAL $", min_value=0.0)
            c_abono = c2.number_input("Abono entregado $", min_value=0.0)
            
            foto = st.camera_input("📸 Evidencia Fotográfica")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            notas = st.text_area("Notas")

            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if c_total > 0 and target_bus != "":
                    img_b64 = process_img(foto)
                    get_ref("maintenance_logs").add({
                        'fleetId': u['fleet'], 'busNumber': target_bus,
                        'category': cat, 'part_name': p_name, 'description': notas,
                        'cost': c_total, 'abono': c_abono,
                        'mechanic': m_sel, 'supplier': c_sel, 'image': img_b64,
                        'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                    })
                    st.success(f"Guardado. Deuda pendiente: ${c_total - c_abono:,.2f}")
                    time.sleep(1); st.rerun()

    # --- HISTORIAL CON WHATSAPP ---
    elif "Historial" in page or "Reportes" in page:
        st.header("📋 Bitácora de Movimientos")
        
        # Obtener mecánicos para sacar sus teléfonos
        all_mecs = {m.to_dict()['name']: m.to_dict().get('phone', '') for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']}
        
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if u['role'] == 'owner':
            bus_sel = st.selectbox("Filtrar Bus:", ["TODOS"] + sorted(list(set([l['busNumber'] for l in logs]))))
            if bus_sel != "TODOS": logs = [l for l in logs if l['busNumber'] == bus_sel]
        else:
            logs = [l for l in logs if l['busNumber'] == u['bus']]

        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            cost = l.get('cost', 0); abono = l.get('abono', 0); deuda = cost - abono
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            status = "full" if deuda <= 0 else ("partial" if abono > 0 else "pending")
            status_txt = "PAGADO" if deuda <= 0 else ("CON ABONO" if abono > 0 else "EN DEUDA")

            st.markdown(f"""
            <div class='bus-card' style='border-left: 8px solid {color}; border-top:none;'>
                <div style='display:flex; justify-content:space-between'>
                    <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l.get('category')}</span>
                    <span class='status-badge {status}'>{status_txt}</span>
                </div>
                <h4 style='margin:10px 0;'>Unidad {l.get('busNumber')} - {l.get('part_name')}</h4>
                <div style='display:flex; justify-content:space-between; font-size:0.9rem'>
                    <span>Total: <b>${cost:,.2f}</b></span>
                    <span>Abonado: <b style='color:#22c55e;'>${abono:,.2f}</b></span>
                    <span style='color:#ef4444'><b>Debe: ${deuda:,.2f}</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("Ver Detalles / Notificar"):
                if l.get('image'): st.image(base64.b64decode(l['image']), use_container_width=True)
                st.write(f"🔧 Mecánico: {l.get('mechanic')} | 🏢 Tienda: {l.get('supplier')}")
                
                # --- SISTEMA DE WHATSAPP ---
                if u['role'] == 'owner':
                    n_pago = st.number_input(f"Añadir nuevo abono", min_value=0.0, max_value=float(deuda), key=f"pay_{l['id']}")
                    
                    col_pay, col_wa = st.columns(2)
                    if col_pay.button("Confirmar Abono", key=f"btn_{l['id']}"):
                        get_ref("maintenance_logs").document(l['id']).update({'abono': abono + n_pago})
                        st.success("¡Abono registrado!")
                        st.rerun()
                    
                    # Botón de WhatsApp
                    tel_mec = all_mecs.get(l.get('mechanic'), "")
                    if tel_mec:
                        # Limpiar teléfono (solo números)
                        tel_clean = "".join(filter(str.isdigit, tel_mec))
                        # Si no tiene código de país, asumimos Ecuador (+593)
                        if len(tel_clean) == 10 and tel_clean.startswith("0"):
                            tel_clean = "593" + tel_clean[1:]
                        elif len(tel_clean) == 9:
                            tel_clean = "593" + tel_clean
                            
                        msg = f"Hola {l.get('mechanic')}, se ha registrado un abono de ${n_pago if n_pago > 0 else abono:,.2f} por el trabajo de {l.get('part_name')} en el Bus {l.get('busNumber')}. Saldo pendiente: ${deuda - n_pago:,.2f}. Gracias."
                        encoded_msg = urllib.parse.quote(msg)
                        wa_url = f"https://wa.me/{tel_clean}?text={encoded_msg}"
                        
                        col_wa.link_button("📱 Notificar por WhatsApp", wa_url, use_container_width=True)
                    else:
                        col_wa.warning("Mecánico sin teléfono guardado.")

    # --- MECÁNICOS ---
    elif "Deudas Mecánicos" in page:
        st.header("👨‍🔧 Cuentas por Mecánico")
        r_logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if r_logs:
            df_m = pd.DataFrame(r_logs)
            df_m['deuda'] = df_m['cost'] - df_m['abono']
            m_sel = st.selectbox("Selecciona mecánico:", df_m['mechanic'].unique())
            res = df_m[df_m['mechanic'] == m_sel]
            st.metric(f"Saldo total con {m_sel}", f"${res['deuda'].sum():,.2f}")
            st.table(res[res['deuda'] > 0][['busNumber', 'part_name', 'deuda']].rename(columns={'busNumber':'Bus', 'part_name':'Trabajo', 'deuda':'Saldo'}))

st.caption(f"Itero V6.1 | Notificaciones WhatsApp Activas | Gestión Profesional | ID: {app_id}")

