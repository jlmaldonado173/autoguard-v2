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
st.set_page_config(page_title="AutoGuard Elite V1.8", layout="wide", page_icon="🚌")

# --- SEMÁFORO DE COLORES POR SECCIÓN ---
CAT_COLORS = {
    "Frenos": "#22c55e",       # Verde (Seguridad)
    "Caja": "#ef4444",         # Rojo (Crítico/Caro)
    "Motor": "#3b82f6",        # Azul (Potencia)
    "Suspensión": "#f59e0b",   # Amarillo (Estabilidad)
    "Llantas": "#a855f7",      # Púrpura (Rodamiento)
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
    
    /* Etiquetas de sección */
    .section-tag {{ padding: 3px 10px; border-radius: 12px; color: white; font-size: 11px; font-weight: bold; }}
    
    /* Estados de pago */
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
        const stored = window.localStorage.getItem('autoguard_v18_user');
        if (stored && !window.parent.location.search.includes('session=')) {
            window.parent.location.search = '?session=' + encodeURIComponent(stored);
        }
        </script>
    """, height=0)

def save_session_js(data):
    components.html(f"<script>window.localStorage.setItem('autoguard_v18_user', '{json.dumps(data)}');</script>", height=0)

def clear_session_js():
    components.html("<script>window.localStorage.removeItem('autoguard_v18_user'); window.parent.location.search = '';</script>", height=0)

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
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite V1.8</h1>", unsafe_allow_html=True)
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
    st.markdown(f"<div class='navbar'><span>👤 {u['name']} | <b>{u['fleet']}</b></span><span>V1.8 ENTERPRISE</span></div>", unsafe_allow_html=True)

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
            pendientes = df[df['paid'] == False]
            
            # Notificaciones de Cambios Posteriores
            proximos = df[df.get('next_change_date', '') != '']
            if not proximos.empty:
                st.warning(f"🔔 Tienes {len(proximos)} cambios de repuestos programados próximamente.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            c2.metric("Deuda Pendiente", f"${pendientes['cost'].sum():,.2f}", delta_color="inverse")
            c3.metric("N° Mantenimientos", len(df))

            st.subheader("📊 Gastos por Sección (Semáforo)")
            # Gráfico de barras con los colores de la marca
            costos_cat = df.groupby('category')['cost'].sum().reset_index()
            st.bar_chart(costos_cat.set_index('category'))
            
            st.subheader("👨‍🔧 Eficiencia de Mecánicos")
            df_mec = df.groupby('mechanic')['cost'].agg(['sum', 'count']).rename(columns={'sum':'Total', 'count':'Trabajos'})
            st.table(df_mec)
        else:
            st.info("No hay datos todavía. Empieza reportando un daño.")

    # --- CASAS COMERCIALES (COMPARACIÓN) ---
    elif menu_opt == "🏢 Casas Comerciales":
        st.header("🏢 Casas Comerciales y Repuestos")
        with st.expander("➕ Registrar Proveedor"):
            with st.form("f_casa"):
                c_n = st.text_input("Nombre de la Casa Comercial")
                c_t = st.text_input("Contacto/WhatsApp")
                if st.form_submit_button("Guardar"):
                    get_ref("suppliers").add({'fleetId':u['fleet'], 'name':c_n, 'phone':c_t})
                    st.success("Proveedor Guardado"); st.rerun()

        st.subheader("💰 Comparativa de Precios por Repuesto")
        logs = [l.to_dict() for l in get_ref("maintenance_logs").stream() if l.to_dict().get('fleetId') == u['fleet']]
        if logs:
            df = pd.DataFrame(logs)
            if 'part_name' in df.columns:
                repuesto_sel = st.selectbox("Selecciona un repuesto para comparar precios", df['part_name'].unique())
                precios = df[df['part_name'] == repuesto_sel].groupby('supplier')['cost'].min().reset_index()
                st.write(f"Precios encontrados para: **{repuesto_sel}**")
                st.dataframe(precios.rename(columns={'supplier':'Casa Comercial', 'cost':'Precio más Bajo'}))

    # --- REPORTAR DAÑO ---
    elif menu_opt == "🛠️ Reportar Daño":
        st.header(f"🛠️ Nuevo Reporte - Unidad {u.get('bus', 'ADMIN')}")
        mecs = [m.to_dict()['name'] for m in get_ref("mechanics").stream() if m.to_dict().get('fleetId') == u['fleet']]
        casas = [c.to_dict()['name'] for c in get_ref("suppliers").stream() if c.to_dict().get('fleetId') == u['fleet']]
        
        with st.form("f_rep"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Sección", list(CAT_COLORS.keys()))
                p_name = st.text_input("Repuesto/Arreglo (Ej: Rodillos, Filtro Aceite)")
                det = st.text_area("Detalle de la falla (Ej: No frena, Suena mucho)")
            with col2:
                cost = st.number_input("Costo Total ($)", min_value=0.0)
                paid = st.checkbox("¿Ya está pagado?")
                next_date = st.date_input("Próximo cambio programado", value=None)
            
            m_sel = st.selectbox("Mecánico", ["No asignado"] + mecs)
            c_sel = st.selectbox("Comprado en (Casa Comercial)", ["Otro"] + casas)
            
            if st.form_submit_button("🚀 GUARDAR REPORTE"):
                get_ref("maintenance_logs").add({
                    'fleetId': u['fleet'], 'busNumber': u.get('bus', 'ADMIN'),
                    'category': cat, 'part_name': p_name, 'description': det,
                    'cost': cost, 'paid': paid, 'mechanic': m_sel, 'supplier': c_sel,
                    'next_change_date': str(next_date) if next_date else "",
                    'date': datetime.now().strftime("%d/%m/%Y"), 'createdAt': datetime.now()
                })
                st.success("✅ ¡Reporte guardado!"); time.sleep(1); st.rerun()

    # --- HISTORIAL Y PAGOS ---
    elif "Historial" in menu_opt:
        st.header("📋 Historial de Pagos y Arreglos")
        logs_ref = get_ref("maintenance_logs").stream()
        logs_list = [{"id": l.id, **l.to_dict()} for l in logs_ref if l.to_dict().get('fleetId') == u['fleet']]
        
        if logs_list:
            for l in sorted(logs_list, key=lambda x: x['createdAt'], reverse=True):
                color = CAT_COLORS.get(l['category'], "#64748b")
                st.markdown(f"""
                <div class='card' style='border-left: 10px solid {color}'>
                    <div style='display:flex; justify-content:space-between'>
                        <span class='section-tag' style='background-color:{color}'>{l['category']}</span>
                        <span class='status-badge {"paid" if l["paid"] else "pending"}'>{"PAGADO" if l["paid"] else "PENDIENTE"}</span>
                    </div>
                    <h4 style='margin-top:10px'>{l.get('part_name', 'Arreglo General')}</h4>
                    <p style='font-size:14px; color:#64748b'>{l['description']}</p>
                    <p><b>Costo:</b> ${l['cost']:,.2f} | <b>Mecánico:</b> {l['mechanic']} | <b>Tienda:</b> {l['supplier']}</p>
                    <small>📅 {l['date']}</small>
                </div>
                """, unsafe_allow_html=True)
                if not l['paid'] and u['role'] == 'owner':
                    if st.button(f"Marcar Pago Realizado (ID: {l['id'][:4]})", key=l['id']):
                        get_ref("maintenance_logs").document(l['id']).update({"paid": True})
                        st.rerun()
        else:
            st.info("Historial vacío.")

st.caption(f"AutoGuard Elite V1.8 | Flota: {u['fleet'] if u else 'N/A'} | Enterprise Mode")

