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
    .main-title { font-size: 55px; font-weight: bold; color: #1E1E1E; text-align: center; margin-bottom: 5px; }
    .stTabs [data-baseweb="tab-list"] { justify-content: center; }
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
MASTER_KEY = "ADMIN123" # Tu clave secreta como dueño de la App

# --- 2. PERSISTENCIA DE SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {
            'role': params.get("r"), 
            'fleet': params.get("f"), 
            'name': params.get("u"), 
            'bus': params.get("b", "0")
        }
        st.rerun()

# --- 3. ACCESO (LOGIN / REGISTRO / MODO DIOS) ---
if 'user' not in st.session_state:
    st.markdown('<div class="main-title">Itaro</div>', unsafe_allow_html=True)
    
    t1, t2, t3 = st.tabs(["👤 Ingreso", "📝 Registro de Flota", "👑 Configuración"])

    with t1: # INGRESO USUARIOS
        with st.container(border=True):
            f_id = st.text_input("Código de Flota").upper().strip()
            u_id = st.text_input("Nombre de Usuario").upper().strip()
            r_id = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            b_id = st.text_input("Unidad/Bus")
            if st.button("ACCEDER"):
                if f_id and u_id:
                    f_doc = FLEETS_REF.document(f_id).get()
                    if f_doc.exists:
                        f_data = f_doc.to_dict()
                        if f_data.get('status') == 'suspended':
                            st.error("🚫 Servicio suspendido. Contacte al proveedor.")
                        else:
                            # Verificación de autorización
                            auth = FLEETS_REF.document(f_id).collection("authorized_users").document(u_id).get()
                            if "Adm" in r_id or auth.exists:
                                u_data = {'role':'owner' if "Adm" in r_id else 'driver', 'fleet':f_id, 'name':u_id, 'bus':b_id if b_id else "0"}
                                st.session_state.user = u_data
                                st.query_params.update({"f":f_id, "u":u_id, "r":u_data['role'], "b":u_data['bus']})
                                st.rerun()
                            else: st.error("❌ Usuario no autorizado.")
                    else: st.error("❌ Flota no existe.")

    with t2: # REGISTRO DE NUEVA FLOTA
        with st.container(border=True):
            st.write("Cree una cuenta para su empresa de transporte.")
            new_f_id = st.text_input("ID Flota (Ej: TAXI-01)").upper().strip()
            owner_n = st.text_input("Nombre del Gerente").upper().strip()
            if st.button("REGISTRAR EMPRESA"):
                if new_f_id and owner_n:
                    f_ref = FLEETS_REF.document(new_f_id)
                    if not f_ref.get().exists:
                        f_ref.set({"owner": owner_n, "status": "active", "created_at": datetime.now()})
                        f_ref.collection("authorized_users").document(owner_n).set({"active": True})
                        st.success("✅ Flota creada. Ya puede ingresar.")
                    else: st.error("❌ El código ya existe.")

    with t3: # MODO DIOS (TÚ)
        m_key = st.text_input("Clave Maestra", type="password")
        if m_key == MASTER_KEY:
            st.subheader("Panel Global")
            for f in FLEETS_REF.stream():
                d = f.to_dict()
                fid = f.id
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2,1,1,1])
                    c1.write(f"🏢 **{fid}**\n{d.get('owner')}")
                    st_now = d.get('status','active')
                    c2.write(f"Estado: {st_now}")
                    if c3.button("PAGO/SUSP.", key=f"s_{fid}"):
                        FLEETS_REF.document(fid).update({"status": "suspended" if st_now == 'active' else 'active'})
                        st.rerun()
                    if c4.button("🗑️ ELIMINAR", key=f"d_{fid}"):
                        FLEETS_REF.document(fid).delete()
                        st.rerun()

# --- 4. PANEL OPERATIVO ---
else:
    u = st.session_state.user
    
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

    st.sidebar.markdown("<h1 style='text-align: center; color: #1E1E1E;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.markdown(f"**Empresa:** {u['fleet']}\n\n**Usuario:** {u['name']}")
    
    menu = ["🏠 Radar Alertas", "🛠️ Taller", "📈 Reportar KM", "💰 Contabilidad", "🏢 Directorio", "👥 Personal"]
    choice = st.sidebar.radio("Navegación", menu if u['role'] == 'owner' else menu[:4])

    # --- RADAR (NOTIFICACIONES CADA 3 DÍAS Y KM) ---
    if choice == "🏠 Radar Alertas":
        st.header("Radar de Unidades")
        bus_list = sorted(df['bus'].unique()) if u['role'] == 'owner' else [u['bus']]
        for b in bus_list:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                maint = b_df[b_df['km_next'] > 0]
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"### Unidad {b}")
                    if (datetime.now() - latest['date']).days >= 3:
                        c1.error("🛑 REQUIERE ACTUALIZAR KM")
                    c2.metric("Kilometraje", f"{latest['km_current']:,.0f}")
                    if not maint.empty:
                        lm = maint.iloc[0]
                        rest = lm['km_next'] - latest['km_current']
                        if rest <= 100: c3.error(f"🚨 URGENTE: {lm['category']}")
                        elif rest <= 500: c3.warning(f"🟡 PRÓXIMO: {lm['category']}")
                        else: c3.success(f"🟢 OK: {lm['category']}")

    # --- REPORTAR KM (VIGILANTE) ---
    elif choice == "📈 Reportar KM":
        st.subheader("Reporte de Kilometraje Actual")
        with st.form("km_rep"):
            nuevo_km = st.number_input("Kilometraje del Tablero", min_value=0)
            if st.form_submit_button("SINCRONIZAR"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": "Actualización KM", "km_current": nuevo_km, "km_next": 0
                })
                st.success("Sincronizado."); time.sleep(1); st.rerun()

    # --- TALLER (REGISTRO + PROGRAMACIÓN) ---
    elif choice == "🛠️ Taller":
        st.subheader("Registro de Mantenimiento")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        with st.form("tall_v"):
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Elemento", ["Aceite", "Frenos", "Llantas", "Caja", "Motor"])
            km_a = c2.number_input("Kilometraje Actual")
            km_p = c2.number_input("KM Próximo Cambio", min_value=km_a)
            st.divider()
            m_n = st.selectbox("Mecánico", ["N/A"] + mecs); m_v = st.number_input("Mano de Obra $")
            c_n = st.selectbox("Comercio", ["N/A"] + coms); c_v = st.number_input("Repuestos $")
            if st.form_submit_button("GUARDAR Y PROGRAMAR ALERTA"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a, "km_next": km_p,
                    "mec_name": m_n, "mec_cost": m_v, "mec_paid": 0,
                    "com_name": c_n, "com_cost": c_v, "com_paid": 0
                })
                st.success("Programado."); time.sleep(1); st.rerun()

    # --- CONTABILIDAD (ABONOS INDEPENDIENTES) ---
    elif choice == "💰 Contabilidad":
        st.header("Contabilidad y Abonos")
        df['d_m'] = df['mec_cost'] - df['mec_paid']
        df['d_c'] = df['com_cost'] - df['com_paid']
        for _, r in df[(df['d_m'] > 0) | (df['d_c'] > 0)].iterrows():
            with st.container(border=True):
                st.write(f"**Bus {r['bus']} - {r['category']}**")
                cm, cc = st.columns(2)
                if r['d_m'] > 0:
                    cm.error(f"🔧 Mecánico: ${r['d_m']:,.0f}")
                    if u['role'] == 'owner':
                        ab = cm.number_input("Abono Mano de Obra", key=f"am_{r['id']}")
                        if cm.button("Pagar", key=f"bm_{r['id']}"):
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(ab)})
                            st.rerun()
                if r['d_c'] > 0:
                    cc.warning(f"📦 Repuestos: ${r['d_c']:,.0f}")
                    if u['role'] == 'owner':
                        ab = cc.number_input("Abono Repuestos", key=f"ac_{r['id']}")
                        if cc.button("Pagar", key=f"bc_{r['id']}"):
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(ab)})
                            st.rerun()

    # --- DIRECTORIO ---
    elif choice == "🏢 Directorio":
        st.subheader("Directorio de Proveedores")
        with st.expander("Añadir Proveedor"):
            with st.form("d"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); tp = st.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    DATA_REF.collection("providers").add({"name":n, "phone":t, "type":tp, "fleetId":u['fleet']})
                    st.rerun()
        for p in providers:
            st.write(f"🔹 **{p['name']}** ({p['type']}) - 📱 {p.get('phone')}")

    # --- PERSONAL ---
    elif choice == "👥 Personal" and u['role'] == 'owner':
        st.subheader("Gestión de Personal")
        n_p = st.text_input("Nombre Conductor").upper().strip()
        if st.button("AUTORIZAR"):
            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(n_p).set({"active": True})
            st.rerun()

    if st.sidebar.button("Salir"):
        st.session_state.clear(); st.rerun()
