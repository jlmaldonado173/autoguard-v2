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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itero Pro", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# Colores de Semáforo (Regla de Jose)
CAT_COLORS = {
    "Frenos": "#22c55e", "Caja": "#ef4444", "Motor": "#3b82f6",
    "Suspensión": "#f59e0b", "Llantas": "#a855f7", "Eléctrico": "#06b6d4",
    "Carrocería": "#ec4899", "Otro": "#64748b"
}

# --- 2. DISEÑO CSS APK ---
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
        background: white; padding: 20px; border-radius: 24px;
        border: 1px solid #e2e8f0; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }}
    .stButton>button {{
        border-radius: 16px; height: 3.5rem; font-weight: 700;
        text-transform: uppercase; width: 100%; transition: all 0.3s;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNCIONES DE APOYO ---
def show_logo(width=150, centered=True):
    if centered:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try: st.image("1000110802.png", use_container_width=True)
            except: st.markdown("<h1 style='text-align:center;'>🔄 ITERO</h1>", unsafe_allow_html=True)
    else:
        try: st.image("1000110802.png", width=width)
        except: st.markdown("### 🔄")

def session_persistence():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('itero_v17_session');
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
app_id = "itero-v15-secure" # Mantener la base estable

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

# --- 6. INTERFAZ DE INGRESO ---
if st.session_state.user is None:
    show_logo()
    st.markdown("<h2 style='text-align:center;'>Seguridad de Flota</h2>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductor", "🛡️ Dueño"])
    with t1:
        with st.form("l_driver"):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                if f_id:
                    fleet_ref = get_ref("fleets").document(f_id).get()
                    if fleet_ref.exists:
                        u_data = {'role':'driver', 'fleet':f_id, 'name':u_n, 'bus':u_b}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_v17_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()
                    else: st.error("❌ Flota no existe")
    with t2:
        with st.form("l_owner"):
            f_o = st.text_input("Código de Flota").upper().strip()
            o_n = st.text_input("Nombre Dueño")
            if st.form_submit_button("Gestionar"):
                if f_o and o_n:
                    fleet_ref = get_ref("fleets").document(f_o).get()
                    if fleet_ref.exists:
                        if fleet_ref.to_dict().get('owner_name') == o_n:
                            u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                            st.session_state.user = u_data
                            js = json.dumps(u_data)
                            components.html(f"<script>window.localStorage.setItem('itero_v17_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                            st.rerun()
                        else: st.error("Nombre de dueño incorrecto")
                    else:
                        get_ref("fleets").document(f_o).set({'owner_name': o_n, 'createdAt': datetime.now()})
                        u_data = {'role':'owner', 'fleet':f_o, 'name':o_n}
                        st.session_state.user = u_data
                        js = json.dumps(u_data)
                        components.html(f"<script>window.localStorage.setItem('itero_v17_session', '{js}'); window.parent.location.search = '?session=' + encodeURIComponent('{js}');</script>", height=0)
                        st.rerun()

# --- 7. APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='top-bar'><span>🛡️ {u['fleet']}</span><span>👤 {u['name']}</span></div><div class='main-content'></div>", unsafe_allow_html=True)

    with st.sidebar:
        show_logo(80, False)
        st.title("Menu")
        opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Historial General", "💰 Contabilidad", "👨‍🔧 Mecánicos"]
        if u['role'] == 'driver': opts = ["🏠 Inicio", "🛠️ Reportar Arreglo", "📋 Mis Reportes"]
        
        sel = st.radio("Ir a:", opts, index=opts.index(st.session_state.page) if st.session_state.page in opts else 0)
        if sel != st.session_state.page:
            st.session_state.page = sel; st.rerun()
            
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.user = None
            components.html("<script>window.localStorage.removeItem('itero_v17_session'); window.parent.location.search = '';</script>", height=0)
            st.rerun()

    # --- PÁGINA: INICIO ---
    if st.session_state.page == "🏠 Inicio":
        st.header(f"📊 Dashboard {u['fleet']}")
        logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            deuda = df['cost'].sum() - df['abono'].sum()
            c1, c2 = st.columns(2)
            c1.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Saldos Pendientes", f"${deuda:,.2f}", delta_color="inverse")
            st.subheader("Estado por Unidades")
            buses = sorted(df['busNumber'].unique())
            cols = st.columns(2)
            for i, b in enumerate(buses):
                with cols[i % 2]:
                    st.markdown(f"<div class='bus-card'><h4>Unidad {b}</h4><p>Gasto: ${df[df['busNumber']==b]['cost'].sum():,.2f}</p></div>", unsafe_allow_html=True)
        else: st.info("Sin registros.")

    # --- PÁGINA: REPORTAR ARREGLO ---
    elif st.session_state.page == "🛠️ Reportar Arreglo":
        st.header("🛠️ Registro de Mantenimiento")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        with st.form("f_rep", clear_on_submit=True):
            bus_n = u.get('bus', "")
            if u['role'] == 'owner': bus_n = st.text_input("N° Unidad")
            cat = st.selectbox("Sección (Semáforo)", list(CAT_COLORS.keys()))
            trabajo = st.text_input("¿Qué se arregló? (Repuestos utilizados)")
            falla = st.text_area("Observación / Falla detectada")
            c1, c2 = st.columns(2)
            total = c1.number_input("Costo Total $", min_value=0.0)
            abono = c2.number_input("Abono hoy $", min_value=0.0)
            m_sel = st.selectbox("Mecánico Encargado", ["Externo"] + mecs)
            if st.form_submit_button("Guardar Reporte"):
                if total > 0 and bus_n:
                    get_ref("logs").add({
                        'fleetId': u['fleet'], 'busNumber': bus_n, 'category': cat,
                        'part': trabajo, 'fault': falla, 'cost': total, 'abono': abono,
                        'mechanic': m_sel, 'date': datetime.now().strftime("%d/%m/%Y"),
                        'createdAt': datetime.now()
                    })
                    st.success("✅ Reporte exitoso"); time.sleep(1); st.session_state.page = "🏠 Inicio"; st.rerun()

    # --- PÁGINA: HISTORIAL GENERAL (ACTUALIZADA) ---
    elif "Historial" in st.session_state.page or "Reportes" in st.session_state.page:
        st.header("📋 Historial Detallado de Flota")
        
        # Obtener todos los reportes de la flota
        raw_logs = [l.to_dict() for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if raw_logs:
            df = pd.DataFrame(raw_logs)
            
            # 1. Filtro por Unidad
            buses = sorted(df['busNumber'].unique())
            bus_filt = st.selectbox("🚛 Filtrar por Unidad:", ["TODOS"] + buses)
            
            # Filtrar lista
            if bus_filt != "TODOS":
                display_logs = [l for l in raw_logs if l.get('busNumber') == bus_filt]
            else:
                display_logs = raw_logs
            
            # 2. Resumen rápido del filtro
            df_filt = pd.DataFrame(display_logs)
            c1, c2, c3 = st.columns(3)
            c1.metric("Cant. Reportes", len(display_logs))
            c2.metric("Inversión en Selección", f"${df_filt['cost'].sum():,.2f}")
            c3.metric("Deuda en Selección", f"${df_filt['cost'].sum() - df_filt['abono'].sum():,.2f}")
            
            st.divider()

            # 3. Listado de tarjetas con detalle solicitado
            for l in sorted(display_logs, key=lambda x: x.get('createdAt', datetime.now()), reverse=True):
                color = CAT_COLORS.get(l.get('category'), "#64748b")
                st.markdown(f"""
                <div class='bus-card' style='border-left: 10px solid {color}'>
                    <div style='display:flex; justify-content:space-between'>
                        <span style='background:{color}; color:white; padding:3px 12px; border-radius:12px; font-size:10px; font-weight:800; text-transform:uppercase;'>{l.get('category')}</span>
                        <span style='color:gray; font-size:12px;'>📅 {l.get('date')}</span>
                    </div>
                    <h3 style='margin:10px 0; color:#1e293b;'>Unidad {l.get('busNumber')} - {l.get('part')}</h3>
                    <p style='font-size:14px; color:#334155; margin-bottom:5px;'><b>👨‍🔧 Mecánico:</b> {l.get('mechanic', 'Externo')}</p>
                    <p style='font-size:14px; color:#334155; margin-bottom:10px;'><b>📝 Observación:</b> {l.get('fault', 'Sin detalles')}</p>
                    <div style='display:flex; justify-content:space-between; align-items:center; border-top: 1px solid #f1f5f9; padding-top:10px;'>
                        <span style='font-size:18px; font-weight:800;'>${l.get('cost', 0):,.2f}</span>
                        <span style='color:{"#16a34a" if l.get("cost")==l.get("abono") else "#ef4444"}; font-weight:bold; font-size:13px;'>
                            {"✅ PAGADO" if l.get("cost")==l.get("abono") else f"🚨 SALDO: ${l.get('cost',0)-l.get('abono',0):,.2f}"}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aún no existen registros en el historial.")

    # --- PÁGINA: CONTABILIDAD ---
    elif st.session_state.page == "💰 Contabilidad":
        st.header("💰 Estado de Cuentas")
        logs = [{"id": l.id, **l.to_dict()} for l in get_ref("logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            df['deuda'] = df['cost'] - df['abono']
            st.subheader("Saldos Pendientes con Mecánicos")
            deudas_mec = df[df['deuda'] > 0].groupby('mechanic')['deuda'].sum().reset_index()
            if not deudas_mec.empty:
                for _, row in deudas_mec.iterrows():
                    with st.expander(f"👤 {row['mechanic']} - Deuda: ${row['deuda']:,.2f}"):
                        items = df[(df['mechanic'] == row['mechanic']) & (df['deuda'] > 0)]
                        for _, item in items.iterrows():
                            st.write(f"Bus {item['busNumber']} | {item['part']} | Saldo: ${item['deuda']}")
            else: st.success("No hay deudas.")
        else: st.info("Sin registros.")

    # --- PÁGINA: MECÁNICOS ---
    elif st.session_state.page == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Directorio")
        with st.form("f_mec"):
            n = st.text_input("Nombre"); t = st.text_input("WhatsApp")
            if st.form_submit_button("Guardar"):
                get_ref("mechanics").add({'fleetId':u['fleet'], 'name':n, 'phone':t}); st.rerun()
        mecs = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        for m in mecs: st.write(f"✅ **{m['name']}** - {m.get('phone')}")

st.caption(f"Itero V17.0 | Historial Inteligente | ID: {app_id}")
