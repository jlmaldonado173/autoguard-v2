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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard Elite V1.9", layout="wide", page_icon="🚌")

# --- SEMÁFORO DE COLORES POR SECCIÓN ---
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- ESTILOS CSS PROFESIONALES ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    .card {{ background: white; padding: 20px; border-radius: 16px; border: 1px solid #e2e8f0; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    .section-tag {{ padding: 3px 10px; border-radius: 12px; color: white; font-size: 11px; font-weight: bold; }}
    .status-badge {{ padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; }}
    .pending {{ background-color: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }}
    .paid {{ background-color: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    .navbar {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 10px 20px; border-radius: 12px; color: white; margin-bottom: 20px; }}
    </style>
    """, unsafe_allow_html=True)

# --- PERSISTENCIA DE SESIÓN ---
def session_persistence_js():
    components.html("""
        <script>
        const stored = window.localStorage.getItem('autoguard_v19_user');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v19_user', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v19_user'); window.parent.location.search = '';</script>", height=0)

# --- FIREBASE ---
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

# --- FUNCIONES DE BASE DE DATOS ---
def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- MANEJO DE SESIÓN ---
u = st.session_state.get('user', None)
if u is None and "session" in st.query_params:
    try: 
        u = json.loads(st.query_params["session"])
        st.session_state.user = u
    except: pass
if u is None: session_persistence_js()

# --- VISTA: LOGIN ---
if u is None:
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite V1.9</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administradores"])
    with t1:
        with st.form("d_login"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                u = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = u
                save_session_js(u); st.rerun()
    with t2:
        with st.form("o_login"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Nombre Admin")
            if st.form_submit_button("Acceso Total"):
                u = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = u
                save_session_js(u); st.rerun()

# --- VISTA: APP PRINCIPAL ---
else:
    st.markdown(f"<div class='navbar'><span>👤 {u['name']} | <b>{u['fleet']}</b></span><span>V1.9 ELITE</span></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("AutoGuard Pro")
        options = ["🏠 Dashboard", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "🛠️ Reportar Daño", "📋 Historial y Pagos", "🧠 Auditoría IA"] if u['role'] == 'owner' else ["🛠️ Reportar Daño", "📋 Mis Reportes"]
        menu_opt = st.radio("Menú", options)
        st.divider()
        if st.sidebar.button("🚪 Cerrar Sesión", type="primary"):
            clear_session_js(); st.session_state.user = None; st.rerun()

    # --- DASHBOARD ---
    if menu_opt == "🏠 Dashboard":
        st.header("📈 Resumen Ejecutivo")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            df = pd.DataFrame(logs)
            
            # SOLUCIÓN AL KEYERROR: Aseguramos que existan todas las columnas necesarias
            for col in ['paid', 'cost', 'category', 'mechanic', 'next_change_date']:
                if col not in df.columns:
                    df[col] = False if col == 'paid' else (0 if col == 'cost' else "")

            pendientes = df[df['paid'] == False]
            
            # Notificaciones
            proximos = df[df['next_change_date'] != '']
            if not proximos.empty:
                st.warning(f"🔔 Tienes {len(proximos)} cambios programados.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Deuda Pendiente", f"${pendientes['cost'].sum():,.2f}", delta_color="inverse")
            c3.metric("N° Mantenimientos", len(df))

            st.subheader("📊 Gastos por Sección")
            costos_cat = df.groupby('category')['cost'].sum().reset_index()
            st.bar_chart(costos_cat.set_index('category'))
        else:
            st.info("👋 ¡Bienvenido, Jose! Aún no hay reportes. Registra el primero para ver las gráficas.")

    # --- MECÁNICOS ---
    elif menu_opt == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Directorio de Mecánicos")
        with st.expander("➕ Registrar Mecánico"):
            with st.form("f_mec"):
                m_n = st.text_input("Nombre")
                m_t = st.text_input("WhatsApp")
                m_e = st.selectbox("Especialidad", list(CAT_COLORS.keys()))
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                    st.success("Registrado"); st.rerun()
        
        m_docs = get_ref("mechanics").stream()
        for m in [d.to_dict() for d in m_docs if d.to_dict().get('fleetId') == u['fleet']]:
            st.markdown(f"**{m['name']}** | 📞 {m['phone']} | 🛠️ {m.get('specialty', 'General')}")

    # --- CASAS COMERCIALES ---
    elif menu_opt == "🏢 Casas Comerciales":
        st.header("🏢 Casas Comerciales")
        with st.expander("➕ Registrar Casa Comercial"):
            with st.form("f_casa"):
                c_n = st.text_input("Nombre")
                c_t = st.text_input("Contacto")
                if st.form_submit_button("Guardar"):
                    get_ref("suppliers").add({'fleetId':u['fleet'], 'name':c_n, 'phone':c_t})
                    st.success("Guardado"); st.rerun()

    # --- REPORTAR DAÑO ---
    elif menu_opt == "🛠️ Reportar Daño":
        st.header(f"🛠️ Reporte Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
                p_name = st.text_input("¿Qué se arregló? (Ej: Rodillos)")
                det = st.text_area("Detalles")
            with col2:
                cost = st.number_input("Costo $", min_value=0.0)
                paid = st.checkbox("¿Pagado?")
                next_d = st.date_input("Próximo cambio", value=None)
            
            m_sel = st.selectbox("Mecánico", ["No asignado"] + mecs)
            c_sel = st.selectbox("Casa Comercial", ["Otro"] + casas)
            
            if st.form_submit_button("🚀 GUARDAR"):
                get_ref("maintenance_logs").add({
                    'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                    'category': cat, 'part_name': p_name, 'description': det,
                    'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                    'next_change_date': str(next_d) if next_d else "",
                    'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("✅ Guardado"); time.sleep(1); st.rerun()

    # --- HISTORIAL ---
    elif "Historial" in menu_opt:
        st.header("📋 Historial y Pagos")
        logs_ref = get_ref("maintenance_logs").stream()
        logs = [{"id": l.id, **l.to_dict()} for l in logs_ref if l.to_dict().get('fleetId') == u['fleet']]
        
        for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
            color = CAT_COLORS.get(l['category'], "#64748b")
            st.markdown(f"""
            <div class='card' style='border-left: 10px solid {color}'>
                <div style='display:flex; justify-content:space-between'>
                    <span class='section-tag' style='background-color:{color}'>{l['category']}</span>
                    <span class='status-badge {"paid" if l.get("paid") else "pending"}'>{"PAGADO" if l.get("paid") else "PENDIENTE"}</span>
                </div>
                <h4 style='margin-top:10px'>{l.get('part_name', 'Arreglo')}</h4>
                <p><b>Mecánico:</b> {l.get('mechanic')} | <b>Costo:</b> ${l['cost']:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
            if not l.get('paid') and u['role'] == 'owner':
                if st.button(f"Pagar Arreglo {l['id'][:4]}", key=l['id']):
                    get_ref("maintenance_logs").document(l['id']).update({"paid": True}); st.rerun()

st.caption(f"AutoGuard Elite V1.9 | Flota: {u['fleet'] if u else 'N/A'}")

