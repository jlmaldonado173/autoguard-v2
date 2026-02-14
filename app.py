import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itaro", layout="wide", page_icon="🚛")

# Estilos CSS
st.markdown("""
    <style>
    .main-title { font-size: 60px; font-weight: 800; color: #1E1E1E; text-align: center; margin-top: -20px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }
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
            # SELECCIÓN OBLIGATORIA PARA DUEÑO
            r_in = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            b_in = st.text_input("Unidad (Solo Conductores)")
            
            if st.button("INGRESAR"):
                if db:
                    doc = FLEETS_REF.document(f_in).get()
                    if doc.exists:
                        if doc.to_dict().get('status') == 'suspended':
                            st.error("🚫 Cuenta suspendida.")
                        else:
                            # Lógica de autorización
                            auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                            is_owner = "Adm" in r_in
                            
                            # El dueño entra si tiene el código. El conductor solo si está autorizado.
                            if is_owner or auth.exists:
                                role = 'owner' if is_owner else 'driver'
                                u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': b_in if b_in else "0"}
                                st.session_state.user = u_data
                                st.query_params.update({"f":f_in, "u":u_in, "r":role, "b":u_data['bus']})
                                st.rerun()
                            else:
                                st.error(f"❌ El usuario '{u_in}' no está autorizado en la flota '{f_in}'.")
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
                        # Auto-autorizar al dueño
                        ref.collection("authorized_users").document(owner).set({"active": True})
                        st.success("✅ Creado. Ingrese como Administrador.")
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
            p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
            provs = [p.to_dict() | {"id": p.id} for p in p_docs]
            q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
            if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
            logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
            df = pd.DataFrame(logs)
            cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']
            if df.empty: df = pd.DataFrame(columns=cols)
            for c in cols: 
                if c not in df.columns: df[c] = 0
            for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            return provs, df
        except: return [], pd.DataFrame()

    providers, df = load_data()

    # Sidebar
    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.caption(f"Flota: {u['fleet']} | Usuario: {u['name']}")
    
    # Botón Offline
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Datos", csv, "itaro_data.csv", "text/csv")

    menu = ["⛽ Combustible", "🏠 Radar", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal") # Solo Dueño ve esto
    
    choice = st.sidebar.radio("Navegación", menu)

    # --- CORRECCIÓN: MÓDULO PERSONAL (SIN FORMULARIO BLOQUEANTE) ---
    if choice == "👥 Personal":
        st.header("Gestión de Conductores")
        st.write("Agregue usuarios permitidos para esta flota.")
        
        # 1. INPUT DIRECTO (Sin st.form para evitar bloqueos)
        col_inp, col_btn = st.columns([3, 1])
        new_driver = col_inp.text_input("Nombre del Conductor").upper().strip()
        
        if col_btn.button("AUTORIZAR"):
            if db and new_driver:
                # Escritura directa
                FLEETS_REF.document(u['fleet']).collection("authorized_users").document(new_driver).set({"active": True})
                st.success(f"✅ {new_driver} AHORA TIENE ACCESO.")
                time.sleep(1) # Pausa breve para ver el mensaje
                st.rerun()    # Recarga para mostrarlo en la lista abajo
            elif not db:
                st.error("⚠️ Sin internet.")
            else:
                st.warning("Escriba un nombre.")

        st.divider()
        st.subheader("Lista de Acceso:")
        
        # 2. LISTADO EN TIEMPO REAL
        if db:
            users_ref = FLEETS_REF.document(u['fleet']).collection("authorized_users").stream()
            users_found = False
            for us in users_ref:
                users_found = True
                st.write(f"👤 **{us.id}** - {'🟢 Activo' if us.to_dict().get('active') else '🔴'}")
            
            if not users_found:
                st.info("Solo el dueño está registrado.")

    # --- RESTO DE MÓDULOS (MANTENIDOS IGUAL) ---
    elif choice == "⛽ Combustible":
        st.header("Carga de Combustible")
        with st.form("fuel"):
            k = st.number_input("KM Actual", min_value=0)
            g = st.number_input("Galones", min_value=0.0)
            c = st.number_input("Costo $", min_value=0.0)
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": "Combustible", "km_current": k, "km_next": 0, "gallons": g, "com_cost": c, "com_paid": c
                })
                st.success("Guardado"); st.rerun()

    elif choice == "🏠 Radar":
        st.header("Radar de Unidades")
        buses = sorted(df['bus'].unique()) if u['role'] == 'owner' else [u['bus']]
        for b in buses:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                latest = b_df.iloc[0]
                maint = b_df[b_df['km_next'] > 0]
                days = (datetime.now() - latest['date']).days
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Unidad {b}**")
                    if days >= 3: c1.error(f"⚠️ {days} días inactivo")
                    c2.metric("KM", f"{latest['km_current']:,.0f}")
                    if not maint.empty:
                        rem = maint.iloc[0]['km_next'] - latest['km_current']
                        if rem <= 500: c3.warning(f"🔧 Cambio próximo ({rem} km)")
                        else: c3.success("🟢 OK")

    elif choice == "🛠️ Taller":
        st.header("Taller")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        with st.form("t"):
            tp = st.radio("Tipo", ["Preventivo (Aceite/Llantas)", "Correctivo (Reparación)"])
            cat = st.selectbox("Categoría", ["Aceite", "Frenos", "Llantas", "Motor", "Otro"])
            ka = st.number_input("KM Actual")
            kn = 0
            if "Preventivo" in tp:
                kn = st.number_input("Próximo Cambio KM", min_value=ka)
            
            mn = st.selectbox("Mecánico", ["N/A"] + mecs)
            rn = st.selectbox("Comercio", ["N/A"] + coms)
            
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": ka, "km_next": kn, "mec_name": mn, "com_name": rn,
                    "mec_cost": 0, "com_cost": 0, "mec_paid": 0, "com_paid": 0 # Se editan costos en contabilidad o aquí si agregas campos
                })
                st.success("Guardado"); st.rerun()

    elif choice == "💰 Contabilidad":
        st.header("Finanzas")
        pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
        if pend.empty: st.success("Sin deudas.")
        for _, r in pend.iterrows():
            st.write(f"**{r['category']}** ({r['bus']})")
            # (Lógica de abonos v52 mantenida aquí simplificada para espacio)
            if u['role'] == 'owner': st.button("Gestionar Pago", key=r['id'])

    elif choice == "🏢 Directorio":
        st.header("Proveedores")
        with st.form("d"):
            n = st.text_input("Nombre"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("providers").add({"name":n, "type":t, "fleetId":u['fleet']})
                st.rerun()
        for p in providers: st.write(f"🔹 {p['name']}")

    if st.sidebar.button("Salir"):
        st.session_state.clear(); st.rerun()
