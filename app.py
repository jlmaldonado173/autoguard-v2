import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y LIBRERÍAS ---
st.set_page_config(page_title="Itaro SaaS Enterprise", layout="wide", page_icon="🏢")

# Intento seguro de cargar gráficos
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error crítico DB: {e}")
            st.stop()
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# CLAVE MAESTRA (TUYA)
MASTER_KEY = "ADMIN123"

# --- 2. SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b")}
        st.rerun()

# --- 3. ACCESO MULTINIVEL (SaaS + CLIENTES) ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Plataforma SaaS")
    
    t_client, t_reg, t_admin = st.tabs(["👤 Ingreso Clientes", "📝 Registrar Nueva Empresa", "👑 Super Admin (Dueño App)"])

    # A. INGRESO DE TUS CLIENTES
    with t_client:
        with st.container(border=True):
            f_in = st.text_input("Código de Empresa").upper().strip()
            u_in = st.text_input("Usuario").upper().strip()
            b_in = st.text_input("Unidad / Bus")
            r_in = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            
            if st.button("INGRESAR"):
                fleet_doc = FLEETS_REF.document(f_in).get()
                if fleet_doc.exists:
                    f_data = fleet_doc.to_dict()
                    
                    # 1. VERIFICAR SI TÚ (SUPER ADMIN) LOS BLOQUEASTE
                    if f_data.get('status') == 'suspended':
                        st.error("🚫 SERVICIO SUSPENDIDO. CONTACTE AL PROVEEDOR DEL SOFTWARE.")
                        st.stop()
                    
                    # 2. VERIFICAR SI EL DUEÑO DE LA FLOTA LOS BLOQUEÓ A ELLOS
                    auth_doc = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                    is_owner = "Adm" in r_in
                    
                    access = False
                    if is_owner: access = True # El dueño siempre entra (si la flota no está suspendida por ti)
                    elif auth_doc.exists and auth_doc.to_dict().get('active', True): access = True
                    
                    if access:
                        u_data = {'role':'owner' if is_owner else 'driver', 'fleet':f_in, 'name':u_in, 'bus':b_in}
                        st.session_state.user = u_data
                        st.query_params.update({"f":f_in, "u":u_in, "b":b_in, "r":u_data['role']})
                        st.rerun()
                    else:
                        st.error("❌ Usuario no autorizado o suspendido por el dueño de la flota.")
                else:
                    st.error("Empresa no encontrada.")

    # B. REGISTRO DE NUEVOS CLIENTES
    with t_reg:
        new_f = st.text_input("ID Nueva Empresa").upper().strip()
        adm_n = st.text_input("Nombre del Cliente (Dueño)").upper().strip()
        if st.button("REGISTRAR CLIENTE"):
            if new_f and not FLEETS_REF.document(new_f).get().exists:
                FLEETS_REF.document(new_f).set({"owner": adm_n, "created": datetime.now(), "status": "active"})
                FLEETS_REF.document(new_f).collection("authorized_users").document(adm_n).set({"active": True})
                st.success("✅ Cliente registrado.")
            else: st.error("ID ya existe.")

    # C. TU PANEL (SUPER ADMIN)
    with t_admin:
        k = st.text_input("Contraseña Maestra", type="password")
        if k == MASTER_KEY:
            st.success("Modo Dios Activado")
            st.divider()
            st.subheader("Gestión Global de Empresas")
            
            # Listar todas las flotas
            all_fleets = FLEETS_REF.stream()
            for f in all_fleets:
                d = f.to_dict()
                status = d.get('status', 'active')
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 2])
                    c1.write(f"🏢 **{f.id}** ({d.get('owner','?')})")
                    if status == 'active':
                        c2.success("ACTIVA")
                        if c3.button("BLOQUEAR", key=f"b_{f.id}"):
                            FLEETS_REF.document(f.id).update({"status": "suspended"})
                            st.rerun()
                    else:
                        c2.error("SUSPENDIDA")
                        if c3.button("REACTIVAR", key=f"r_{f.id}"):
                            FLEETS_REF.document(f.id).update({"status": "active"})
                            st.rerun()

# --- 4. SISTEMA OPERATIVO COMPLETO (SOLO SI HAY SESIÓN) ---
else:
    u = st.session_state.user
    
    # Verificación continua de bloqueo SaaS
    f_status = FLEETS_REF.document(u['fleet']).get().to_dict().get('status', 'active')
    if f_status == 'suspended':
        st.error("🚫 SU SERVICIO HA SIDO SUSPENDIDO. CERRANDO SESIÓN...")
        time.sleep(3); st.session_state.clear(); st.rerun()

    # --- MOTOR DE DATOS BLINDADO (v38) ---
    def load_full_data():
        # Proveedores
        p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = []
        for p in p_docs:
            d = p.to_dict()
            if 'name' not in d: d['name'] = "Desconocido" # Blindaje
            d['id'] = p.id
            provs.append(d)
        
        # Logs
        q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
        logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
        
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'mec_name', 'com_name']
        df = pd.DataFrame(logs) if logs else pd.DataFrame(columns=cols)
        
        for c in cols: 
            if c not in df.columns: 
                df[c] = 0 if 'cost' in c or 'paid' in c or 'km' in c else "N/A"
        
        for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        return provs, df

    providers, df = load_full_data()
    p_phones = {p.get('name'): p.get('phone') for p in providers}

    # --- NAVEGACIÓN ---
    st.sidebar.title(f"📱 {u['fleet']}")
    menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal")
    
    choice = st.sidebar.radio("Menú", menu)

    # --- MÓDULO 1: DASHBOARD ---
    if choice == "🏠 Inicio":
        st.subheader(f"Estado Unidad {u['bus']}")
        if not df.empty:
            latest = df[df['bus'] == u['bus']].sort_values('date', ascending=False)
            if not latest.empty:
                row = latest.iloc[0]
                km_r = row['km_next'] - row['km_current']
                c1, c2 = st.columns(2)
                c1.metric("KM Actual", f"{row['km_current']:,.0f}")
                c2.metric("Próximo Servicio", f"{km_r:,.0f} KM", delta_color="inverse" if km_r < 500 else "normal")
            else: st.info("Sin registros.")
        else: st.info("Bienvenido.")

    # --- MÓDULO 2: TALLER (Conexión Directorio) ---
    elif choice == "🛠️ Taller":
        st.subheader("Registrar Mantenimiento")
        mecs = [p['name'] for p in providers if p.get('type') == "Mecánico"]
        coms = [p['name'] for p in providers if p.get('type') == "Comercio"]
        
        with st.form("taller_form"):
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Otros"])
            k_a = col2.number_input("KM Actual", min_value=0)
            k_p = col2.number_input("Próximo Cambio", min_value=k_a)
            st.divider()
            c_m, c_c = st.columns(2)
            m_sel = c_m.selectbox("Mecánico", ["N/A"] + mecs)
            m_val = c_m.number_input("Mano de Obra $", min_value=0.0)
            c_sel = c_c.selectbox("Comercio", ["N/A"] + coms)
            c_val = c_c.number_input("Repuestos $", min_value=0.0)
            
            if st.form_submit_button("GUARDAR"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": k_a, "km_next": k_p,
                    "mec_name": m_sel, "mec_cost": m_val, "mec_paid": 0,
                    "com_name": c_sel, "com_cost": c_val, "com_paid": 0
                })
                st.success("Guardado."); time.sleep(1); st.rerun()

    # --- MÓDULO 3: CONTABILIDAD (Pagos + WhatsApp) ---
    elif choice == "💰 Contabilidad":
        st.header("Finanzas")
        df['d_m'] = df['mec_cost'] - df['mec_paid']
        df['d_c'] = df['com_cost'] - df['com_paid']
        df['total'] = df['d_m'] + df['d_c']
        
        if PLOTLY_AVAILABLE and u['role'] == 'owner' and not df.empty:
            g = df.groupby('bus')['total'].sum().reset_index()
            st.plotly_chart(px.bar(g, x='bus', y='total', title="Deuda Total"))

        for _, r in df[df['total'] > 1].iterrows():
            with st.container(border=True):
                st.write(f"**Bus {r['bus']} - {r['category']}** ({r['date'].date()})")
                c1, c2 = st.columns(2)
                if r['d_m'] > 0: c1.error(f"Mecánico: ${r['d_m']:,.0f}")
                if r['d_c'] > 0: c2.warning(f"Repuestos: ${r['d_c']:,.0f}")
                
                if u['role'] == 'owner':
                    with st.expander("Pagar"):
                        dest = st.radio("Pagar a", ["Mecánico", "Comercio"], key=f"d_{r['id']}")
                        amt = st.number_input("Monto", key=f"a_{r['id']}")
                        if st.button("Confirmar", key=f"b_{r['id']}"):
                            field = "mec_paid" if dest == "Mecánico" else "com_paid"
                            DATA_REF.collection("logs").document(r['id']).update({field: firestore.Increment(amt)})
                            
                            p_name = r['mec_name'] if dest == "Mecánico" else r['com_name']
                            tel = p_phones.get(p_name, "")
                            msg = f"Pago de ${amt} registrado por {r['category']}."
                            st.markdown(f"[📲 Enviar Comprobante WA](https://wa.me/{tel}?text={urllib.parse.quote(msg)})")
                            time.sleep(2); st.rerun()

    # --- MÓDULO 4: DIRECTORIO ---
    elif choice == "🏢 Directorio":
        st.subheader("Proveedores")
        with st.form("new_pr"):
            n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); tipo = st.selectbox("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar"):
                DATA_REF.collection("providers").add({"name":n, "phone":t, "type":tipo, "fleetId":u['fleet']})
                st.rerun()
        for p in providers:
            st.write(f"🔹 **{p['name']}** ({p.get('type','?')}) - {p.get('phone','')}")

    # --- MÓDULO 5: PERSONAL (SOLO DUEÑO FLOTA) ---
    elif choice == "👥 Personal" and u['role'] == 'owner':
        st.subheader("Gestión de Conductores")
        with st.form("add_u"):
            n_user = st.text_input("Nombre Conductor").upper().strip()
            if st.form_submit_button("Autorizar"):
                FLEETS_REF.document(u['fleet']).collection("authorized_users").document(n_user).set({"active": True})
                st.success("Autorizado"); time.sleep(1); st.rerun()
        
        users = FLEETS_REF.document(u['fleet']).collection("authorized_users").stream()
        for us in users:
            d_u = us.to_dict()
            st.write(f"👤 **{us.id}** - {'🟢 Activo' if d_u.get('active') else '🔴 Inactivo'}")
            if st.button("Cambiar Estado", key=f"s_{us.id}"):
                FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).update({"active": not d_u.get('active')})
                st.rerun()

    if st.sidebar.button("Salir"):
        st.session_state.clear()
        st.rerun()
