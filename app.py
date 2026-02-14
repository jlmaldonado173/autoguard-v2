import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itaro", layout="wide", page_icon="🚜")

# Estilo para el Logo y Título Limpio
st.markdown("""
    <style>
    .main-title { font-size: 50px; font-weight: bold; color: #1E1E1E; text-align: center; margin-bottom: 0px; }
    .logo-container { display: flex; justify-content: center; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")
MASTER_KEY = "ADMIN123"

# --- 2. PERSISTENCIA ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b", "0")}
        st.rerun()

# --- 3. ACCESO (LOGIN / REGISTRO / MODO DIOS) ---
if 'user' not in st.session_state:
    st.markdown('<div class="main-title">Itaro</div>', unsafe_allow_html=True)
    # Aquí puedes poner el link de tu logo si lo tienes en internet
    # st.image("https://tu-link-de-logo.com/logo.png", width=200) 
    
    t1, t2, t3 = st.tabs(["👤 Ingreso", "📝 Registro", "👑 Configuración"])

    with t1:
        with st.container(border=True):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_id = st.text_input("Usuario").upper().strip()
            r_id = st.selectbox("Rol", ["Conductor", "Administrador/Dueño"])
            b_id = st.text_input("Unidad (Solo Choferes)")
            if st.button("ACCEDER"):
                if f_id and u_id:
                    f_doc = FLEETS_REF.document(f_id).get()
                    if f_doc.exists:
                        if f_doc.to_dict().get('status') == 'suspended':
                            st.error("🚫 Cuenta suspendida. Contacte soporte.")
                        else:
                            u_data = {'role':'owner' if "Adm" in r_id else 'driver', 'fleet':f_id, 'name':u_id, 'bus':b_id if b_id else "0"}
                            st.session_state.user = u_data
                            st.query_params.update({"f":f_id, "u":u_id, "r":u_data['role'], "b":u_data['bus']})
                            st.rerun()
                    else: st.error("Flota no registrada.")

    with t3: # MODO DIOS (ELIMINAR / SUSPENDER)
        if st.text_input("Master Key", type="password") == MASTER_KEY:
            st.subheader("Control Maestro Itaro")
            for f in FLEETS_REF.stream():
                d = f.to_dict()
                fid = f.id
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2,1,1,1])
                    c1.write(f"🏢 **{fid}**\n{d.get('owner')}")
                    c2.write(f"Estado: {d.get('status')}")
                    if c3.button("SUSPENDER/ACTIVAR", key=f"s_{fid}"):
                        new_s = "suspended" if d.get('status') == 'active' else 'active'
                        FLEETS_REF.document(fid).update({"status": new_s})
                        st.rerun()
                    if c4.button("🗑️ ELIMINAR", key=f"d_{fid}"):
                        FLEETS_REF.document(fid).delete()
                        st.rerun()

# --- 4. PANEL OPERATIVO ITARO ---
else:
    u = st.session_state.user
    
    # Motor de datos blindado
    def load_data():
        p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
        logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
        df = pd.DataFrame(logs)
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'mec_name', 'com_name']
        if df.empty: df = pd.DataFrame(columns=cols)
        for c in cols: 
            if c not in df.columns: df[c] = 0
        for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df

    providers, df = load_data()

    # Interfaz
    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.markdown(f"**Flota:** {u['fleet']}\n\n**Usuario:** {u['name']}")
    
    menu = ["🏠 Radar Alertas", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio", "👥 Personal"]
    choice = st.sidebar.radio("Ir a:", menu if u['role'] == 'owner' else menu[:4])

    # --- RADAR (3 DÍAS + KM) ---
    if choice == "🏠 Radar Alertas":
        st.header("Radar de Unidades")
        bus_list = df['bus'].unique()
        for b in bus_list:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                maint = b_df[b_df['km_next'] > 0]
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"### Unidad {b}")
                    # Alerta tiempo
                    if (datetime.now() - latest['date']).days >= 3:
                        c1.error("REQUIERE ACTUALIZAR KM")
                    c2.metric("Kilometraje", f"{latest['km_current']:,.0f}")
                    # Alerta Mecánica
                    if not maint.empty:
                        lm = maint.iloc[0]
                        rest = lm['km_next'] - latest['km_current']
                        if rest <= 100: c3.error(f"URGENTE: {lm['category']}")
                        elif rest <= 500: c3.warning(f"PRÓXIMO: {lm['category']}")
                        else: c3.success(f"OK: {lm['category']}")

    # --- ABONOS QUIRÚRGICOS ---
    elif choice == "💰 Contabilidad":
        st.header("Contabilidad de Arreglos")
        df['d_m'] = df['mec_cost'] - df['mec_paid']
        df['d_c'] = df['com_cost'] - df['com_paid']
        for _, r in df[(df['d_m'] > 0) | (df['d_c'] > 0)].iterrows():
            with st.container(border=True):
                st.write(f"**Bus {r['bus']} - {r['category']}**")
                col_m, col_c = st.columns(2)
                if r['d_m'] > 0:
                    col_m.write(f"Deuda Mecánico: ${r['d_m']:,.0f}")
                    if u['role'] == 'owner':
                        ab_m = col_m.number_input("Abono Mecánico", key=f"m_{r['id']}")
                        if col_m.button("Pagar Mano de Obra", key=f"bm_{r['id']}"):
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(ab_m)})
                            st.rerun()
                if r['d_c'] > 0:
                    col_c.write(f"Deuda Repuestos: ${r['d_c']:,.0f}")
                    if u['role'] == 'owner':
                        ab_c = col_c.number_input("Abono Repuestos", key=f"c_{r['id']}")
                        if col_c.button("Pagar Repuestos", key=f"bc_{r['id']}"):
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(ab_c)})
                            st.rerun()

    # --- DIRECTORIO VINCULADO ---
    elif choice == "🏢 Directorio":
        st.subheader("Directorio de Proveedores Itaro")
        with st.expander("Agregar Proveedor"):
            with st.form("dir_form"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); tp = st.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    DATA_REF.collection("providers").add({"name":n, "phone":t, "type":tp, "fleetId":u['fleet']})
                    st.rerun()
        for p in providers:
            st.write(f"🔹 **{p['name']}** ({p['type']}) - {p.get('phone')}")

    if st.sidebar.button("Cerrar Sesión"):
        st.query_params.clear()
        st.session_state.clear()
        st.rerun()
