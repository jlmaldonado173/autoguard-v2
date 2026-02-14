import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse # Para crear los links de WhatsApp

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro", layout="wide", page_icon="🚛")

st.markdown("""
    <style>
    .main-title { font-size: 60px; font-weight: 800; color: #1E1E1E; text-align: center; margin-top: -20px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }
    .status-active { color: green; font-weight: bold; }
    .status-inactive { color: red; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN BLINDADA (OFFLINE) ---
@st.cache_resource
def init_db():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception:
        return None

db = init_db()
APP_ID = "itero-titanium-v15"
MASTER_KEY = "ADMIN123"

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

# --- 4. ACCESO ---
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
                    doc = FLEETS_REF.document(f_in).get()
                    if doc.exists:
                        if doc.to_dict().get('status') == 'suspended':
                            st.error("🚫 Cuenta suspendida.")
                        else:
                            auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                            is_owner = "Adm" in r_in
                            
                            if is_owner or (auth.exists and auth.to_dict().get('active', True)):
                                role = 'owner' if is_owner else 'driver'
                                u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': b_in if b_in else "0"}
                                st.session_state.user = u_data
                                st.query_params.update({"f":f_in, "u":u_in, "r":role, "b":u_data['bus']})
                                st.rerun()
                            else: st.error("❌ Usuario no autorizado o suspendido.")
                    else: st.error("❌ Flota no encontrada.")
                else: st.error("⚠️ Sin conexión.")

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
                        ref.collection("authorized_users").document(owner).set({"active": True, "role": "admin"})
                        st.success("✅ Creado.")
                    else: st.error("Código ocupado.")

    with t3: # ADMIN
        if st.text_input("Llave Maestra", type="password") == MASTER_KEY and db:
            for f in FLEETS_REF.stream():
                c1, c2 = st.columns([3,1])
                c1.write(f"🏢 {f.id} ({f.to_dict().get('status')})")
                if c2.button("DEL", key=f.id):
                    FLEETS_REF.document(f.id).delete(); st.rerun()

# --- 5. SISTEMA OPERATIVO ---
else:
    u = st.session_state.user
    
    def load_data():
        if not db: return [], pd.DataFrame()
        try:
            # Proveedores
            p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
            provs = [p.to_dict() | {"id": p.id} for p in p_docs]
            
            # Historial
            q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
            if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
            logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
            
            df = pd.DataFrame(logs)
            cols = ['bus', 'category', 'observations', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
            if df.empty: df = pd.DataFrame(columns=cols)
            
            for c in cols: 
                if c not in df.columns: 
                    df[c] = "" if c == 'observations' else 0 # Observaciones texto, resto 0
            
            for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            return provs, df
        except: return [], pd.DataFrame()

    providers, df = load_data()
    
    # Mapa de teléfonos para WhatsApp automático
    phone_map = {p['name']: p.get('phone', '') for p in providers}

    # Sidebar
    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.caption(f"Usuario: {u['name']}")
    
    # Botón Offline
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Datos", csv, "itaro_data.csv", "text/csv")

    menu = ["⛽ Combustible", "🏠 Radar", "🔍 Buscador", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal")
    
    choice = st.sidebar.radio("Navegación", menu)

    # --- 1. GESTIÓN DE PERSONAL (COMPLETA) ---
    if choice == "👥 Personal":
        st.header("Gestión de Conductores")
        
        with st.expander("➕ Agregar Nuevo Conductor", expanded=True):
            with st.form("new_driver"):
                c1, c2, c3 = st.columns(3)
                d_name = c1.text_input("Nombre Completo").upper().strip()
                d_ced = c2.text_input("Cédula")
                d_tel = c3.text_input("Teléfono")
                if st.form_submit_button("GUARDAR"):
                    if db and d_name:
                        FLEETS_REF.document(u['fleet']).collection("authorized_users").document(d_name).set({
                            "active": True, "cedula": d_ced, "phone": d_tel, "date": datetime.now().isoformat()
                        })
                        st.success("Guardado."); time.sleep(1); st.rerun()
                    else: st.error("Nombre requerido o sin conexión.")
        
        st.write("### Lista de Personal")
        if db:
            users_ref = FLEETS_REF.document(u['fleet']).collection("authorized_users").stream()
            for us in users_ref:
                d = us.to_dict()
                if d.get('role') != 'admin': # No mostrar al dueño para no auto-borrarse
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                        status = "🟢 Activo" if d.get('active', True) else "🔴 Suspendido"
                        c1.write(f"**{us.id}**")
                        c1.caption(f"Cédula: {d.get('cedula','--')} | Tel: {d.get('phone','--')}")
                        c2.write(status)
                        
                        # Suspender
                        btn_label = "🔒" if d.get('active', True) else "🔓"
                        if c3.button(btn_label, key=f"s_{us.id}", help="Suspender/Activar"):
                            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).update({"active": not d.get('active', True)})
                            st.rerun()
                        
                        # Eliminar
                        if c4.button("🗑️", key=f"d_{us.id}", help="Eliminar permanentemente"):
                            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).delete()
                            st.rerun()

    # --- 2. BUSCADOR POR PALABRAS ---
    elif choice == "🔍 Buscador":
        st.header("Historial de Mantenimiento")
        search = st.text_input("🔎 Buscar (Ej: 'Aceite', 'Frenos', 'Roto')", placeholder="Escribe aquí...")
        
        if not df.empty:
            # Filtrar
            if search:
                mask = df.apply(lambda row: search.lower() in str(row['category']).lower() or search.lower() in str(row['observations']).lower(), axis=1)
                results = df[mask]
            else:
                results = df
            
            st.dataframe(results[['date', 'bus', 'category', 'observations', 'km_current', 'mec_cost', 'com_cost']].sort_values('date', ascending=False), hide_index=True)
        else:
            st.info("No hay registros aún.")

    # --- 3. CONTABILIDAD (CON WHATSAPP) ---
    elif choice == "💰 Contabilidad":
        st.header("Finanzas y Pagos")
        
        # Comparativa de Unidades (Solo Dueño)
        if u['role'] == 'owner' and not df.empty:
            st.subheader("Comparativa de Gastos")
            df['total_cost'] = df['mec_cost'] + df['com_cost']
            gastos = df.groupby('bus')['total_cost'].sum().reset_index()
            st.dataframe(gastos, hide_index=True)
        
        st.subheader("Cuentas por Pagar")
        df['d_m'] = df['mec_cost'] - df['mec_paid']
        df['d_c'] = df['com_cost'] - df['com_paid']
        pend = df[(df['d_m'] > 0) | (df['d_c'] > 0)]
        
        if pend.empty: st.success("Todo pagado.")
        
        for _, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"📅 {r['date'].date()} | **Bus {r['bus']}** - {r['category']}")
                st.caption(f"Obs: {r['observations']}")
                
                c1, c2 = st.columns(2)
                
                # Pago Mecánico
                if r['d_m'] > 0:
                    c1.error(f"🔧 Mecánico ({r.get('mec_name','NA')}): ${r['d_m']:,.2f}")
                    if u['role'] == 'owner':
                        v = c1.number_input("Abonar", key=f"vm_{r['id']}")
                        if c1.button("Pagar", key=f"bm_{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(v)})
                            # Link WhatsApp
                            tel = phone_map.get(r.get('mec_name'), '')
                            msg = f"Hola, le realizamos un abono de ${v} por el trabajo de {r['category']} en la unidad {r['bus']}."
                            link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                            c1.markdown(f"[📲 Enviar Comprobante WA]({link})", unsafe_allow_html=True)
                            
                # Pago Comercio
                if r['d_c'] > 0:
                    c2.warning(f"📦 Repuestos ({r.get('com_name','NA')}): ${r['d_c']:,.2f}")
                    if u['role'] == 'owner':
                        v = c2.number_input("Abonar", key=f"vc_{r['id']}")
                        if c2.button("Pagar", key=f"bc_{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(v)})
                            # Link WhatsApp
                            tel = phone_map.get(r.get('com_name'), '')
                            msg = f"Hola, le realizamos un abono de ${v} por los repuestos de {r['category']} para la unidad {r['bus']}."
                            link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                            c2.markdown(f"[📲 Enviar Comprobante WA]({link})", unsafe_allow_html=True)

    # --- 4. TALLER (MÁS OPCIONES Y OBS) ---
    elif choice == "🛠️ Taller":
        st.header("Registro de Mantenimiento")
        
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("taller_full"):
            tipo = st.radio("Tipo", ["Mantenimiento Preventivo (Aceite/Frenos/Llantas)", "Reparación Correctiva (Daños/Carrocería)"])
            
            c1, c2 = st.columns(2)
            cats = ["Aceite Motor", "Aceite Caja", "Aceite Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Carrocería", "Vidrios", "Tapicería", "Otro"]
            cat = c1.selectbox("Categoría Detallada", cats)
            obs = c2.text_area("Observaciones (Marca, detalles...)", height=1)
            
            ka = c1.number_input("KM Actual", min_value=0)
            kn = 0
            if "Preventivo" in tipo:
                kn = c2.number_input("Próximo Cambio a los...", min_value=ka)
                st.caption("ℹ️ Generará alerta.")
            
            st.divider()
            col_m, col_r = st.columns(2)
            mn = col_m.selectbox("Mecánico", ["N/A"] + mecs); mc = col_m.number_input("Mano Obra $")
            rn = col_r.selectbox("Comercio", ["N/A"] + coms); rc = col_r.number_input("Repuestos $")
            
            if st.form_submit_button("GUARDAR"):
                if db:
                    DATA_REF.collection("logs").add({
                        "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                        "category": cat, "observations": obs, 
                        "km_current": ka, "km_next": kn,
                        "mec_name": mn, "mec_cost": mc, "mec_paid": 0,
                        "com_name": rn, "com_cost": rc, "com_paid": 0
                    })
                    st.success("Guardado"); time.sleep(1); st.rerun()
                else: st.error("Sin internet")

    # --- 5. DIRECTORIO (CON TELÉFONO OBLIGATORIO) ---
    elif choice == "🏢 Directorio":
        st.header("Proveedores")
        with st.form("add_prov"):
            n = st.text_input("Nombre / Local")
            p = st.text_input("WhatsApp (con código país, ej: 593...)")
            t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar"):
                if db and n and p:
                    DATA_REF.collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":u['fleet']})
                    st.rerun()
                else: st.warning("Nombre y WhatsApp requeridos")
        
        for p in providers:
            st.write(f"🔹 **{p['name']}** - 📞 {p.get('phone')} ({p['type']})")

    # --- 6. RADAR Y COMBUSTIBLE (RESUMIDOS) ---
    elif choice == "🏠 Radar":
        st.header("Radar de Unidades")
        # ... (Lógica de radar v54 mantenida)
        buses = sorted(df['bus'].unique()) if u['role'] == 'owner' else [u['bus']]
        for b in buses:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                days = (datetime.now() - latest['date']).days
                with st.container(border=True):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Unidad {b}**")
                    if days >= 3: c1.error(f"⚠️ {days} días inactivo")
                    c2.metric("KM", f"{latest['km_current']:,.0f}")

    elif choice == "⛽ Combustible":
        st.header("Carga de Combustible")
        with st.form("fuel"):
            k = st.number_input("KM Actual", min_value=0)
            g = st.number_input("Galones"); c = st.number_input("Costo $")
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": "Combustible", "observations": "Carga normal",
                    "km_current": k, "km_next": 0, "gallons": g, "com_cost": c, "com_paid": c
                })
                st.success("Guardado"); st.rerun()

    if st.sidebar.button("Salir"):
        st.session_state.clear(); st.rerun()
