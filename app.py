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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="AutoGuard V4.0", layout="wide", page_icon="🚌", initial_sidebar_state="collapsed")

CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4", "Otro": "#64748b"
}

# --- 2. CSS PREMIUM (SISTEMA DE PAGOS) ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .stApp {{ background-color: #f1f5f9; }}
    
    .top-app-bar {{
        background: #1e293b; color: white; padding: 15px 20px;
        position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
        display: flex; justify-content: space-between; align-items: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }}
    .main-content {{ margin-top: 75px; }}
    
    .card {{ 
        background: white; padding: 20px; border-radius: 20px; 
        border: 1px solid #e2e8f0; margin-bottom: 12px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.02); 
    }}
    
    .money-row {{ display: flex; justify-content: space-between; margin-top: 10px; border-top: 1px solid #f1f5f9; padding-top: 10px; }}
    .debt-text {{ color: #ef4444; font-weight: 800; font-size: 1.1rem; }}
    .paid-text {{ color: #22c55e; font-weight: 800; font-size: 1.1rem; }}
    
    .status-badge {{ padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: bold; }}
    .pending {{ background: #fee2e2; color: #ef4444; }}
    .partial {{ background: #fef3c7; color: #d97706; }}
    .full {{ background: #dcfce7; color: #16a34a; }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES TÉCNICAS ---
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
    components.html(f"<script>window.localStorage.setItem('autoguard_v40_session', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v40_session'); window.parent.location.search = '';</script>", height=0)

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

# --- 5. SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "🏠 Dashboard"

if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass

# --- 6. ACCESO ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center;'>🛡️ AutoGuard Elite V4.0</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administración"])
    with t1:
        with st.form("l_d"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus (Ej: 1535)")
            if st.form_submit_button("Ingresar"):
                u = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = u
                save_session_js(u); st.rerun()
    with t2:
        with st.form("l_o"):
            f_o = st.text_input("Código de Flota")
            o_n = st.text_input("Dueño")
            if st.form_submit_button("Acceso Total"):
                u = {'role':'owner', 'fleet':f_o.upper().strip(), 'name':o_n}
                st.session_state.user = u
                save_session_js(u); st.rerun()

# --- 7. APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-app-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("AutoGuard")
        menu = ["🏠 Dashboard", "🛠️ Reportar Daño", "📋 Historial y Deudas", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales"]
        if u['role'] == 'driver': menu = ["🏠 Dashboard", "🛠️ Reportar Daño", "📋 Mis Reportes"]
        
        sel = st.radio("Navegación", menu, index=menu.index(st.session_state.page) if st.session_state.page in menu else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel
            st.rerun()
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- LÓGICA DE PÁGINAS ---

    if st.session_state.page == "🏠 Dashboard":
        st.header("📊 Finanzas de Flota")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            df = pd.DataFrame(logs)
            # Asegurar columnas financieras
            for col in ['cost', 'abono', 'busNumber', 'mechanic']:
                if col not in df.columns: df[col] = 0.0 if col in ['cost', 'abono'] else "S/N"
            
            df['deuda'] = df['cost'] - df['abono']

            # Filtro por bus si es dueño
            if u['role'] == 'owner':
                bus_filter = st.selectbox("🎯 Filtrar por Bus:", ["TODOS"] + sorted(list(df['busNumber'].unique())))
                if bus_filter != "TODOS": df = df[df['busNumber'] == bus_filter]
            else:
                df = df[df['busNumber'] == u['bus']]

            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Total Abonado", f"${df['abono'].sum():,.2f}")
            c3.metric("DEUDA ACTUAL", f"${df['deuda'].sum():,.2f}", delta_color="inverse")

            st.subheader("🛠️ Deuda por Mecánico")
            resumen_mec = df.groupby('mechanic')['deuda'].sum().reset_index()
            st.dataframe(resumen_mec[resumen_mec['deuda'] > 0].rename(columns={'mechanic':'Mecánico', 'deuda':'Monto por Pagar'}))
        else:
            st.info("No hay registros aún.")

    elif st.session_state.page == "🛠️ Reportar Daño":
        st.subheader(f"🛠️ Reporte Bus {u.get('bus', 'ADMIN')}")
        try: mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        except: mecs = []
        try: casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        except: casas = []

        with st.form("f_finanzas"):
            cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
            p_name = st.text_input("¿Qué se arregló?")
            
            col_a, col_b = st.columns(2)
            cost_total = col_a.number_input("Costo TOTAL del trabajo $", min_value=0.0)
            abono_inicial = col_b.number_input("Abono realizado hoy $", min_value=0.0)
            
            foto = st.camera_input("📸 Foto del arreglo/factura")
            m_sel = st.selectbox("Mecánico", ["Externo"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            det = st.text_area("Notas adicionales")

            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                if cost_total > 0:
                    with st.spinner("Guardando finanzas..."):
                        img_data = process_img(foto)
                        get_ref("maintenance_logs").add({
                            'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                            'category': cat, 'part_name': p_name, 'description': det,
                            'cost': cost_total, 'abono': abono_inicial,
                            'mechanic': m_sel, 'supplier': c_sel, 'image': img_data,
                            'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                        })
                        st.success(f"Registrado. Deuda pendiente: ${cost_total - abono_inicial:,.2f}")
                        time.sleep(1); st.session_state.page = "🏠 Dashboard"; st.rerun()

    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial Detallado y Abonos")
        logs_ref = get_ref("maintenance_logs").stream()
        logs = [{"id": l.id, **l.to_dict()} for l in logs_ref if l.to_dict().get('fleetId') == u['fleet']]
        
        if u['role'] == 'driver': logs = [l for l in logs if l.get('busNumber') == u['bus']]

        for l in sorted(logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
            cost = l.get('cost', 0)
            abono = l.get('abono', 0)
            deuda = cost - abono
            color = CAT_COLORS.get(l.get('category'), "#64748b")
            
            status = "full" if deuda <= 0 else ("partial" if abono > 0 else "pending")
            status_txt = "PAGADO" if deuda <= 0 else ("CON ABONO" if abono > 0 else "SIN PAGAR")

            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span style='background:{color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;'>{l.get('category')}</span>
                    <span class='status-badge {status}'>{status_txt}</span>
                </div>
                <h4 style='margin:10px 0;'>Bus {l.get('busNumber')} - {l.get('part_name')}</h4>
                <p style='font-size:14px;'>🛠️ <b>Mecánico:</b> {l.get('mechanic')}</p>
                <div class='money-row'>
                    <span>Total: <b>${cost:,.2f}</b></span>
                    <span>Abonado: <b style='color:#22c55e;'>${abono:,.2f}</b></span>
                    <span class='debt-text'>Debe: ${deuda:,.2f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Detalles / Abonos"):
                if l.get('image'): st.image(base64.b64decode(l['image']), use_container_width=True)
                st.write(f"📝 {l.get('description')}")
                
                if deuda > 0 and u['role'] == 'owner':
                    nuevo_abono = st.number_input(f"Añadir abono (ID: {l['id'][:4]})", min_value=0.0, max_value=deuda)
                    if st.button(f"Confirmar Abono", key=f"btn_{l['id']}"):
                        get_ref("maintenance_logs").document(l['id']).update({'abono': abono + nuevo_abono})
                        st.success("Abono registrado"); st.rerun()

st.caption(f"AutoGuard V4.0 | Finanzas y Gestión de Abonos Activa | ID: {app_id}")

