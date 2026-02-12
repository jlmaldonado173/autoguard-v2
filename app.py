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
st.set_page_config(page_title="AutoGuard Elite V1.7", layout="wide", page_icon="🚌")

# --- MAPA DE COLORES POR SECCIÓN ---
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde
    "Caja": "#ef4444",         # Rojo
    "Motor": "#3b82f6",        # Azul
    "Suspensión": "#f59e0b",   # Amarillo
    "Llantas": "#a855f7",      # Púrpura
    "Eléctrico": "#06b6d4",    # Cian
    "Otro": "#64748b"          # Gris
}

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="st-"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: #f8fafc; }}
    
    .card {{ background: white; padding: 24px; border-radius: 16px; border: 1px solid #e2e8f0; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    
    /* Etiquetas de colores */
    .tag {{ padding: 4px 12px; border-radius: 20px; color: white; font-size: 12px; font-weight: bold; text-transform: uppercase; }}
    {"".join([f".tag-{k} {{ background-color: {v}; }}" for k, v in CAT_COLORS.items()])}
    
    .status-pending {{ color: #ef4444; font-weight: bold; border: 1px solid #ef4444; padding: 2px 8px; border-radius: 5px; }}
    .status-paid {{ color: #22c55e; font-weight: bold; border: 1px solid #22c55e; padding: 2px 8px; border-radius: 5px; }}
    
    .logout-bar {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 12px 20px; border-radius: 12px; color: white; margin-bottom: 25px; }}
    </style>
    """, unsafe_allow_html=True)

# --- PERSISTENCIA DE SESIÓN ---
def session_persistence_js():
    components.html("""
        <script>
        const storedUser = window.localStorage.getItem('autoguard_v17_user');
        if (storedUser && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(storedUser);
        }
        </script>
    """, height=0)

def save_session_js(data):
    json_data = json.dumps(data)
    components.html(f"<script>window.localStorage.setItem('autoguard_v17_user', '{json_data}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v17_user'); window.parent.location.search = '';</script>", height=0)

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
apiKey = "" # Gemini

# --- FUNCIONES DE BASE DE DATOS ---
def get_ref(col):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection(col)

# --- MANEJO DE SESIÓN ---
if 'user' not in st.session_state: st.session_state.user = None
if 'menu_option' not in st.session_state: st.session_state.menu_option = "🏠 Dashboard"

if st.session_state.user is None and "session" in st.query_params:
    try: st.session_state.user = json.loads(st.query_params["session"])
    except: pass

if st.session_state.user is None: session_persistence_js()

# --- VISTA: LOGIN ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite V1.7</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;'>Gestión de Costos, Mecánicos y Repuestos</p>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "🛡️ Administradores"])
    with t1:
        with st.form("d_login"):
            f_id = st.text_input("Código de Flota")
            u_n = st.text_input("Nombre")
            u_b = st.text_input("N° Bus")
            if st.form_submit_button("Ingresar"):
                user = {'role':'driver', 'fleet':f_id.upper().strip(), 'name':u_n, 'bus':u_b}
                st.session_state.user = user
                save_session_js(user); st.rerun()
    with t2:
        with st.form("o_login"):
            f_id_o = st.text_input("Código de Flota")
            u_n_o = st.text_input("Nombre Admin")
            if st.form_submit_button("Acceso Total"):
                user = {'role':'owner', 'fleet':f_id_o.upper().strip(), 'name':u_n_o}
                st.session_state.user = user
                save_session_js(user); st.rerun()

# --- VISTA: APP PRINCIPAL ---
else:
    u = st.session_state.user
    st.markdown(f"<div class='logout-bar'><span>👤 {u['name']} | <b>{u['fleet']}</b></span><span>V1.7 PRO</span></div>", unsafe_allow_html=True)

    with st.sidebar:
        st.title("AutoGuard")
        if u['role'] == 'owner':
            options = ["🏠 Dashboard", "👨‍🔧 Mecánicos", "🏢 Casas Comerciales", "📦 Inventario", "📋 Historial Pagos", "🧠 Análisis IA"]
        else:
            options = ["🛠️ Reportar Daño", "📋 Mis Reportes"]
        for opt in options:
            if st.sidebar.button(opt, use_container_width=True):
                st.session_state.menu_option = opt
        st.divider()
        if st.sidebar.button("🚪 Cerrar Sesión", type="primary", use_container_width=True):
            clear_session_js(); st.session_state.user = None; st.rerun()

    opt = st.session_state.menu_option

    # --- DASHBOARD ---
    if opt == "🏠 Dashboard":
        st.header("📈 Resumen de Flota")
        
        # Alertas de cambios posteriores (Próximos servicios)
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            # Notificación de cambios pendientes
            pendientes = df[df['paid'] == False]
            if not pendientes.empty:
                st.error(f"⚠️ Tienes {len(pendientes)} pagos pendientes a mecánicos o casas comerciales.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Gasto Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Pendiente de Pago", f"${pendientes['cost'].sum():,.2f}")
            c3.metric("Mantenimientos", len(df))

            st.subheader("Inversión por Sistema (Colores)")
            costos_cat = df.groupby('category')['cost'].sum().reset_index()
            # Gráfico de barras coloreado
            st.bar_chart(costos_cat.set_index('category'))
            
            st.subheader("🔍 Desglose por Arreglos")
            for cat, color in CAT_COLORS.items():
                cat_data = df[df['category'] == cat]
                if not cat_data.empty:
                    st.markdown(f"<span class='tag' style='background-color:{color}'>{cat}</span> {len(cat_data)} arreglos realizados.", unsafe_allow_html=True)

    # --- MECÁNICOS ---
    elif opt == "👨‍🔧 Mecánicos":
        st.header("👨‍🔧 Comparación de Mecánicos")
        m_list = [m.to_dict() for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        
        with st.expander("🆕 Registrar Mecánico"):
            with st.form("f_mec"):
                m_n = st.text_input("Nombre")
                m_t = st.text_input("Teléfono")
                m_e = st.selectbox("Especialidad Principal", list(CAT_COLORS.keys()))
                if st.form_submit_button("Guardar"):
                    get_ref("mechanics").add({'fleetId':u['fleet'], 'name':m_n, 'phone':m_t, 'specialty':m_e})
                    st.success("Registrado"); st.rerun()
        
        if m_list and logs:
            df_m = pd.DataFrame(m_list)
            df_l = pd.DataFrame(logs)
            comparison = df_l.groupby('mechanic')['cost'].agg(['sum', 'count']).reset_index()
            st.subheader("Ranking de Gastos por Mecánico")
            st.dataframe(comparison.rename(columns={'mechanic':'Mecánico', 'sum':'Costo Total', 'count':'N° Trabajos'}))
        else:
            st.info("Registra mecánicos y arreglos para ver comparativas.")

    # --- CASAS COMERCIALES ---
    elif opt == "🏢 Casas Comerciales":
        st.header("🏢 Comparación de Casas Comerciales (Repuestos)")
        st.write("Registra tus proveedores y compara dónde es más barato comprar.")
        
        with st.expander("➕ Añadir Proveedor/Casa Comercial"):
            with st.form("f_casa"):
                c_n = st.text_input("Nombre de la Casa Comercial")
                c_d = st.text_input("Ubicación/Contacto")
                if st.form_submit_button("Registrar Proveedor"):
                    get_ref("suppliers").add({'fleetId':u['fleet'], 'name':c_n, 'contact':c_d})
                    st.success("Proveedor añadido"); st.rerun()
        
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df_l = pd.DataFrame(logs)
            if 'supplier' in df_l.columns:
                comp_casas = df_l.groupby('supplier')['cost'].sum().reset_index()
                st.bar_chart(comp_casas.set_index('supplier'))
            else:
                st.info("Empieza a reportar compras para comparar casas comerciales.")

    # --- REPORTAR DAÑO (MODIFICADO) ---
    elif opt == "🛠️ Reportar Daño":
        st.header(f"🛠️ Reporte Detallado - Unidad {u.get('bus')}")
        
        # Cargar datos para selects
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep_v17"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Sección (Color)", list(CAT_COLORS.keys()))
                sub_cat = st.text_input("Arreglo específico (Ej: Cambio de Rodillos, Sin Frenos)")
            with col2:
                cost = st.number_input("Costo Total ($)", min_value=0.0)
                paid = st.checkbox("¿Ya está pagado?")
            
            m_sel = st.selectbox("Mecánico responsable", ["Externo/No registrado"] + mecs)
            c_sel = st.selectbox("Casa Comercial (Donde se compró)", ["Ninguna/Otro"] + casas)
            desc = st.text_area("Notas adicionales")
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                get_ref("maintenance_logs").add({
                    'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                    'category': cat, 'detail': sub_cat, 'description': desc,
                    'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                    'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("¡Reporte guardado con éxito!"); time.sleep(1); st.rerun()

    # --- HISTORIAL Y PAGOS ---
    elif opt == "📋 Historial Pagos":
        st.header("📋 Control de Pagos y Deudas")
        logs_ref = get_ref("maintenance_logs").stream()
        logs = [{"id": l.id, **l.to_dict()} for l in logs_ref if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs:
            for l in sorted(logs, key=lambda x: x['createdAt'], reverse=True):
                color = CAT_COLORS.get(l['category'], "#64748b")
                status_class = "status-paid" if l['paid'] else "status-pending"
                status_text = "PAGADO" if l['paid'] else "PENDIENTE"
                
                with st.container():
                    st.markdown(f"""
                    <div class='card' style='border-left: 8px solid {color}'>
                        <div style='display:flex; justify-content:space-between'>
                            <span class='tag' style='background-color:{color}'>{l['category']}</span>
                            <span class='{status_class}'>{status_text}</span>
                        </div>
                        <h4 style='margin:10px 0'>{l['detail'] if l.get('detail') else l['category']}</h4>
                        <p><b>Mecánico:</b> {l.get('mechanic')} | <b>Casa Comercial:</b> {l.get('supplier')}</p>
                        <p><b>Costo:</b> ${l['cost']:,.2f} | 📅 {l['date']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if not l['paid'] and u['role'] == 'owner':
                        if st.button(f"Marcar como Pagado (ID: {l['id'][:5]})", key=l['id']):
                            get_ref("maintenance_logs").document(l['id']).update({"paid": True})
                            st.success("Pago registrado"); st.rerun()
        else:
            st.info("No hay historial de arreglos.")

    # --- ANÁLISIS IA ---
    elif opt == "🧠 Análisis IA":
        st.header("🧠 Auditoría Inteligente Gemini")
        st.write("Analizando la eficiencia de tus mecánicos y los precios de las casas comerciales...")
        
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            if st.button("🪄 Ejecutar Auditoría Global"):
                summary = f"Datos de Flota: {str(logs)[:3000]}"
                # Llamada simulada para ejemplo (requiere apiKey en Secrets)
                st.info("Gemini está analizando tendencias de costos y desempeño...")
        else:
            st.warning("Necesito datos para realizar la auditoría.")

st.caption(f"AutoGuard Elite V1.7 | Flota: {u['fleet'] if u else 'N/A'} | Colores por Sección Activos")

