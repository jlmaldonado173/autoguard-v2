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

# Estilo Limpio: Solo ITARO
st.markdown("""
    <style>
    .main-title { font-size: 60px; font-weight: 800; color: #1E1E1E; text-align: center; margin-top: -20px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }
    .stAlert { font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN BLINDADA (OFFLINE MODE) ---
@st.cache_resource
def init_db():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception:
        return None # Si no hay internet, devuelve None para no romper la app

db = init_db()
APP_ID = "itero-titanium-v15"
MASTER_KEY = "ADMIN123"

# Referencias seguras (solo si hay conexión)
if db:
    FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
    DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b", "0")
        }
        st.rerun()

# --- 4. PANTALLA DE ACCESO ---
if 'user' not in st.session_state:
    st.markdown('<div class="main-title">Itaro</div>', unsafe_allow_html=True)
    
    t1, t2, t3 = st.tabs(["👤 Ingresar", "📝 Crear Flota", "⚙️ Admin"])

    with t1: # LOGIN
        with st.container(border=True):
            f_in = st.text_input("Código de Flota").upper().strip()
            u_in = st.text_input("Usuario").upper().strip()
            r_in = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            b_in = st.text_input("Unidad (Solo Conductores)")
            
            if st.button("INGRESAR"):
                if db:
                    try:
                        doc = FLEETS_REF.document(f_in).get()
                        if doc.exists:
                            if doc.to_dict().get('status') == 'suspended':
                                st.error("🚫 Cuenta suspendida. Contacte soporte.")
                            else:
                                auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                                if "Adm" in r_in or auth.exists:
                                    u_data = {'role':'owner' if "Adm" in r_in else 'driver', 'fleet':f_in, 'name':u_in, 'bus':b_in if b_in else "0"}
                                    st.session_state.user = u_data
                                    st.query_params.update({"f":f_in, "u":u_in, "r":u_data['role'], "b":u_data['bus']})
                                    st.rerun()
                                else: st.error("Usuario no autorizado.")
                        else: st.error("Flota no encontrada.")
                    except: st.warning("⚠️ Error de conexión. Intente más tarde.")
                else: st.error("⚠️ Sin conexión a internet.")

    with t2: # REGISTRO
        with st.container(border=True):
            st.info("Nueva Empresa")
            new_id = st.text_input("Crear Código").upper().strip()
            owner = st.text_input("Nombre Dueño").upper().strip()
            if st.button("REGISTRAR EMPRESA"):
                if db and new_id and owner:
                    ref = FLEETS_REF.document(new_id)
                    if not ref.get().exists:
                        ref.set({"owner": owner, "status": "active", "created": datetime.now()})
                        ref.collection("authorized_users").document(owner).set({"active": True})
                        st.success("✅ Creado exitosamente.")
                    else: st.error("Código ocupado.")
                elif not db: st.error("⚠️ Sin internet.")

    with t3: # MODO DIOS
        if st.text_input("Llave Maestra", type="password") == MASTER_KEY:
            if db:
                st.write("### Control Global")
                for f in FLEETS_REF.stream():
                    d = f.to_dict()
                    c1, c2, c3 = st.columns([2,1,1])
                    c1.write(f"🏢 **{f.id}** ({d.get('status')})")
                    if c2.button("SUSPENDER", key=f"s_{f.id}"):
                        ns = "suspended" if d.get('status') == 'active' else "active"
                        FLEETS_REF.document(f.id).update({"status": ns})
                        st.rerun()
                    if c3.button("ELIMINAR", key=f"d_{f.id}"):
                        FLEETS_REF.document(f.id).delete()
                        st.rerun()

# --- 5. SISTEMA OPERATIVO ---
else:
    u = st.session_state.user
    
    # Carga de Datos Blindada (Funciona sin internet devolviendo vacío)
    def load_data():
        if not db: return [], pd.DataFrame()
        try:
            # Proveedores
            p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
            provs = [p.to_dict() | {"id": p.id} for p in p_docs]
            
            # Logs
            q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
            if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
            logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
            
            df = pd.DataFrame(logs)
            cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'gallons']
            if df.empty: df = pd.DataFrame(columns=cols)
            
            for c in cols: 
                if c not in df.columns: df[c] = 0
            
            # Limpieza numérica
            num_cols = ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'gallons']
            for nc in num_cols:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            return provs, df
        except:
            return [], pd.DataFrame() # Retorno seguro si falla la carga

    providers, df = load_data()

    # Barra Lateral
    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.caption(f"Flota: {u['fleet']} | Usuario: {u['name']}")
    
    # RESPALDO OFFLINE (CSV)
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Respaldo (Offline)", csv, "itaro_backup.csv", "text/csv")
    elif not db:
        st.sidebar.error("⚠️ MODO OFFLINE ACTIVADO")

    menu = ["⛽ Combustible & KM", "🏠 Radar Alertas", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio", "👥 Personal"]
    choice = st.sidebar.radio("Navegación", menu if u['role'] == 'owner' else menu[:5])

    # --- 1. COMBUSTIBLE & KM ---
    if choice == "⛽ Combustible & KM":
        st.header("Carga de Combustible")
        st.info("Registrar aquí actualiza el Kilometraje para las alertas.")
        with st.form("fuel"):
            c1, c2 = st.columns(2)
            km = c1.number_input("KM Actual (Tablero)", min_value=0)
            gl = c2.number_input("Galones", min_value=0.0)
            co = c2.number_input("Costo $", min_value=0.0)
            
            if st.form_submit_button("GUARDAR"):
                if db:
                    DATA_REF.collection("logs").add({
                        "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                        "category": "Combustible", "km_current": km, "km_next": 0,
                        "gallons": gl, "com_cost": co, "com_paid": co, "mec_cost": 0, "mec_paid": 0
                    })
                    st.success("✅ Guardado."); time.sleep(1); st.rerun()
                else: st.warning("⚠️ Sin conexión. Espere a tener señal.")

    # --- 2. RADAR ALERTAS ---
    elif choice == "🏠 Radar Alertas":
        st.header("Radar de Unidades")
        bus_list = sorted(df['bus'].unique()) if u['role'] == 'owner' else [u['bus']]
        
        for b in bus_list:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                # Buscar mantenimientos preventivos pendientes
                maint = b_df[b_df['km_next'] > 0]
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.subheader(f"Unidad {b}")
                    
                    # Regla 3 Días
                    days = (datetime.now() - latest['date']).days
                    if days >= 3: c1.error(f"⚠️ {days} días sin reporte")
                    else: c1.caption(f"Hace {days} días")
                    
                    c2.metric("KM Actual", f"{latest['km_current']:,.0f}")
                    
                    # Semáforo Mantenimiento
                    if not maint.empty:
                        # Buscar el más urgente
                        maint['diff'] = maint['km_next'] - latest['km_current']
                        urgente = maint.sort_values('diff').iloc[0]
                        rem = urgente['diff']
                        
                        if rem <= 100: c3.error(f"🚨 CAMBIAR YA: {urgente['category']}")
                        elif rem <= 500: c3.warning(f"🟡 PRÓXIMO: {urgente['category']}")
                        else: c3.success(f"🟢 OK: {urgente['category']}")
                    else: c3.info("Todo al día.")

    # --- 3. TALLER INTELIGENTE ---
    elif choice == "🛠️ Taller":
        st.subheader("Registro de Taller")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("taller"):
            tipo = st.radio("Tipo", ["Mantenimiento Preventivo (Aceite, Llantas)", "Reparación Correctiva (Focos, Daños)"])
            c_cat, c_km = st.columns(2)
            
            cat = c_cat.selectbox("Categoría", ["Aceite", "Caja", "Motor", "Llantas", "Eléctrico", "Carrocería", "Otro"])
            ka = c_km.number_input("KM Actual", min_value=0)
            
            kn = 0
            if "Preventivo" in tipo:
                kn = c_km.number_input("¿Próximo cambio a los...?", min_value=ka)
                st.caption("ℹ️ Generará alerta de kilometraje.")
            
            st.divider()
            c_m, c_r = st.columns(2)
            mn = c_m.selectbox("Mecánico", ["N/A"] + mecs); mc = c_m.number_input("Mano de Obra $")
            rn = c_r.selectbox("Comercio", ["N/A"] + coms); rc = c_r.number_input("Repuestos $")
            
            if st.form_submit_button("GUARDAR"):
                if db:
                    DATA_REF.collection("logs").add({
                        "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                        "category": cat, "km_current": ka, "km_next": kn,
                        "mec_name": mn, "mec_cost": mc, "mec_paid": 0,
                        "com_name": rn, "com_cost": rc, "com_paid": 0
                    })
                    st.success("✅ Guardado."); time.sleep(1); st.rerun()
                else: st.warning("⚠️ Sin internet.")

    # --- 4. CONTABILIDAD (ABONOS) ---
    elif choice == "💰 Contabilidad":
        st.header("Cuentas por Pagar")
        df['d_m'] = df['mec_cost'] - df['mec_paid']
        df['d_c'] = df['com_cost'] - df['com_paid']
        pend = df[(df['d_m'] > 0) | (df['d_c'] > 0)]
        
        if pend.empty: st.success("🎉 Sin deudas.")
        
        for _, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"**{r['category']}** (Bus {r['bus']}) - {r['date'].date()}")
                c1, c2 = st.columns(2)
                
                if r['d_m'] > 0:
                    c1.error(f"🔧 Mecánico: ${r['d_m']:,.2f}")
                    if u['role'] == 'owner':
                        v = c1.number_input("Abonar", key=f"m{r['id']}")
                        if c1.button("Pagar", key=f"bm{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(v)})
                            st.rerun()
                
                if r['d_c'] > 0:
                    c2.warning(f"📦 Repuestos: ${r['d_c']:,.2f}")
                    if u['role'] == 'owner':
                        v = c2.number_input("Abonar", key=f"c{r['id']}")
                        if c2.button("Pagar", key=f"bc{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(v)})
                            st.rerun()

    # --- 5. DIRECTORIO ---
    elif choice == "🏢 Directorio":
        st.header("Proveedores")
        with st.expander("Nuevo"):
            with st.form("d"):
                n = st.text_input("Nombre"); p = st.text_input("WhatsApp"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    if db:
                        DATA_REF.collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":u['fleet']})
                        st.rerun()
                    else: st.warning("⚠️ Sin internet.")
        for p in providers:
            st.write(f"🔹 **{p['name']}** ({p['type']}) 📞 {p.get('phone')}")

    # --- 6. PERSONAL ---
    elif choice == "👥 Personal" and u['role'] == 'owner':
        st.header("Conductores")
        with st.form("u"):
            nm = st.text_input("Nombre Exacto").upper().strip()
            if st.form_submit_button("AUTORIZAR"):
                if db:
                    FLEETS_REF.document(u['fleet']).collection("authorized_users").document(nm).set({"active": True})
                    st.success("OK"); st.rerun()
                else: st.warning("⚠️ Sin internet.")
        
        if db:
            usrs = FLEETS_REF.document(u['fleet']).collection("authorized_users").stream()
            for us in usrs:
                st.write(f"👤 {us.id} - {'🟢' if us.to_dict().get('active') else '🔴'}")

    if st.sidebar.button("Salir"):
        st.session_state.clear(); st.rerun()
