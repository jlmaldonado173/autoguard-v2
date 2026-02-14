import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="Itaro", layout="wide", page_icon="🚛")

# Estilos CSS: Limpieza y Botones Profesionales
st.markdown("""
    <style>
    .main-title { font-size: 60px; font-weight: 800; color: #1E1E1E; text-align: center; margin-top: -20px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }
    /* Botón Rojo para Cerrar Sesión y Eliminar */
    div[data-testid="stSidebar"] .stButton:last-child button {
        background-color: #FF4B4B; color: white; border: none;
    }
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
        return None # Retorna None si no hay internet

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

# --- 4. ACCESO (LOGIN / REGISTRO / ADMIN) ---
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
                            st.error("🚫 CUENTA SUSPENDIDA.")
                        else:
                            # Verificación de acceso
                            auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                            is_owner = "Adm" in r_in
                            
                            # Entra si es dueño O si es conductor activo
                            if is_owner or (auth.exists and auth.to_dict().get('active', True)):
                                role = 'owner' if is_owner else 'driver'
                                u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': b_in if b_in else "0"}
                                st.session_state.user = u_data
                                st.query_params.update({"f":f_in, "u":u_in, "r":role, "b":u_data['bus']})
                                st.rerun()
                            else: st.error("❌ No autorizado o suspendido.")
                    else: st.error("❌ Flota no existe.")
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

    with t3: # MODO DIOS
        if st.text_input("Llave Maestra", type="password") == MASTER_KEY and db:
            st.write("### Control Global")
            for f in FLEETS_REF.stream():
                d = f.to_dict()
                st_now = d.get('status', 'active')
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                    c1.write(f"🏢 **{f.id}** ({d.get('owner')})")
                    
                    if st_now == 'active':
                        c2.success("ACTIVA")
                        if c3.button("SUSPENDER", key=f"s_{f.id}"):
                            FLEETS_REF.document(f.id).update({"status": "suspended"}); st.rerun()
                    else:
                        c2.error("SUSPENDIDA")
                        if c3.button("ACTIVAR", key=f"s_{f.id}"):
                            FLEETS_REF.document(f.id).update({"status": "active"}); st.rerun()
                            
                    if c4.button("🗑️", key=f"d_{f.id}"):
                        FLEETS_REF.document(f.id).delete(); st.rerun()

# --- 5. SISTEMA OPERATIVO ---
else:
    u = st.session_state.user
    
    # Carga de Datos Segura
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
                if c not in df.columns: df[c] = "" if c == 'observations' else 0 
            
            for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            return provs, df
        except: return [], pd.DataFrame()

    providers, df = load_data()
    phone_map = {p['name']: p.get('phone', '') for p in providers}

    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.caption(f"Usuario: {u['name']}")
    
    # Botón de Respaldo
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Datos", csv, "itaro_data.csv", "text/csv")

    menu = ["⛽ Combustible", "🏠 Radar", "🔍 Buscador", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal")
    
    choice = st.sidebar.radio("Navegación", menu)

    # --- 1. PERSONAL (COMPLETO) ---
    if choice == "👥 Personal":
        st.header("Gestión de Conductores")
        with st.expander("➕ Agregar Conductor", expanded=True):
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
        
        st.subheader("Nómina Activa")
        if db:
            users_ref = FLEETS_REF.document(u['fleet']).collection("authorized_users").stream()
            for us in users_ref:
                d = us.to_dict()
                if d.get('role') != 'admin':
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                        st_icon = "🟢" if d.get('active', True) else "🔴"
                        c1.write(f"**{us.id}**")
                        c1.caption(f"🆔 {d.get('cedula','--')} | 📞 {d.get('phone','--')}")
                        c2.write(st_icon)
                        
                        if c3.button("🔒/🔓", key=f"s_{us.id}"):
                            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).update({"active": not d.get('active', True)})
                            st.rerun()
                        if c4.button("🗑️", key=f"d_{us.id}"):
                            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).delete()
                            st.rerun()

    # --- 2. BUSCADOR ---
    elif choice == "🔍 Buscador":
        st.header("Buscador Inteligente")
        search = st.text_input("Buscar (Ej: Aceite, Focos)...")
        if not df.empty and search:
            mask = df.apply(lambda row: search.lower() in str(row['category']).lower() or search.lower() in str(row['observations']).lower(), axis=1)
            st.dataframe(df[mask][['date', 'bus', 'category', 'observations', 'km_current']].sort_values('date', ascending=False), hide_index=True)
        elif not df.empty:
            st.dataframe(df[['date', 'bus', 'category', 'observations']].head(10), hide_index=True)

    # --- 3. CONTABILIDAD (SINCRONIZADA + WHATSAPP) ---
    elif choice == "💰 Contabilidad":
        st.header("Finanzas")
        if u['role'] == 'owner' and not df.empty:
            st.info("Resumen de Gastos Totales")
            df['total'] = df['mec_cost'] + df['com_cost']
            st.bar_chart(df.groupby('bus')['total'].sum())

        st.subheader("Pagos Pendientes")
        pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
        if pend.empty: st.success("Todo al día.")
        
        for _, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"**{r['category']}** (Bus {r['bus']}) - {r['date'].date()}")
                c1, c2 = st.columns(2)
                
                # Deuda Mecánico
                dm = r['mec_cost'] - r['mec_paid']
                if dm > 0:
                    c1.error(f"Mecánico: ${dm:,.2f}")
                    if u['role'] == 'owner':
                        v = c1.number_input("Abonar", key=f"m{r['id']}")
                        if c1.button("Pagar", key=f"bm{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(v)})
                            tel = phone_map.get(r.get('mec_name'), '')
                            msg = f"Abono de ${v} por {r['category']}."
                            c1.markdown(f"[📲 Enviar Comprobante]({f'https://wa.me/{tel}?text={urllib.parse.quote(msg)}'})")

                # Deuda Comercio
                dc = r['com_cost'] - r['com_paid']
                if dc > 0:
                    c2.warning(f"Repuestos: ${dc:,.2f}")
                    if u['role'] == 'owner':
                        v = c2.number_input("Abono", key=f"c{r['id']}")
                        if c2.button("Pagar", key=f"bc{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(v)})
                            tel = phone_map.get(r.get('com_name'), '')
                            msg = f"Abono de ${v} por repuestos {r['category']}."
                            c2.markdown(f"[📲 Enviar Comprobante]({f'https://wa.me/{tel}?text={urllib.parse.quote(msg)}'})")

    # --- 4. TALLER (CON ABONO INICIAL) ---
    elif choice == "🛠️ Taller":
        st.header("Mantenimiento")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("taller_full"):
            tipo = st.radio("Tipo", ["Preventivo (Alerta)", "Correctivo (Solo Registro)"])
            c1, c2 = st.columns(2)
            cats = ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Carrocería", "Vidrios", "Otro"]
            cat = c1.selectbox("Categoría", cats)
            obs = c2.text_area("Observaciones (Marca, detalles)")
            ka = c1.number_input("KM Actual", min_value=0)
            kn = 0
            if "Preventivo" in tipo:
                kn = c2.number_input("Próximo Cambio", min_value=ka)
            
            st.divider()
            c3, c4 = st.columns(2)
            
            # --- SECCIÓN SINCRONIZADA ---
            mn = c3.selectbox("Mecánico", ["N/A"] + mecs)
            mc = c3.number_input("Costo Mano de Obra ($)", min_value=0.0)
            mp = c3.number_input("Abono Inicial Mecánico ($)", min_value=0.0, max_value=mc, help="Lo que paga hoy")

            rn = c4.selectbox("Comercio", ["N/A"] + coms)
            rc = c4.number_input("Costo Repuestos ($)", min_value=0.0)
            cp = c4.number_input("Abono Inicial Repuestos ($)", min_value=0.0, max_value=rc, help="Lo que paga hoy")
            
            if st.form_submit_button("GUARDAR"):
                if db:
                    DATA_REF.collection("logs").add({
                        "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                        "category": cat, "observations": obs, 
                        "km_current": ka, "km_next": kn,
                        "mec_name": mn, "mec_cost": mc, "mec_paid": mp, 
                        "com_name": rn, "com_cost": rc, "com_paid": cp
                    })
                    st.success("Guardado."); time.sleep(1); st.rerun()
                else: st.error("Sin internet")

    # --- 5. DIRECTORIO (WHATSAPP) ---
    elif choice == "🏢 Directorio":
        st.header("Proveedores")
        with st.expander("➕ Nuevo"):
            with st.form("d"):
                n = st.text_input("Nombre").upper(); p = st.text_input("WhatsApp (con código)"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar") and db and n:
                    DATA_REF.collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":u['fleet']})
                    st.rerun()
        
        if providers:
            for p in providers:
                with st.container(border=True):
                    c1, c2 = st.columns([3,1])
                    icon = "🔧" if p.get('type') == "Mecánico" else "📦"
                    c1.write(f"**{icon} {p['name']}**\n{p.get('phone')}")
                    
                    phone = p.get('phone', '').replace('+', '').strip()
                    if phone:
                        link = f"https://wa.me/{phone}"
                        c2.markdown(f'''<a href="{link}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366; color:white; padding:5px; border-radius:5px; text-align:center;">Chat</div></a>''', unsafe_allow_html=True)

    # --- 6. RADAR & GAS ---
    elif choice == "🏠 Radar":
        st.subheader("Radar")
        buses = sorted(df['bus'].unique()) if u['role'] == 'owner' else [u['bus']]
        for b in buses:
            b_df = df[df['bus'] == b].sort_values('date', ascending=False)
            if not b_df.empty:
                lat = b_df.iloc[0]
                days = (datetime.now() - lat['date']).days
                
                # Check mantenimientos
                maint = b_df[b_df['km_next'] > 0]
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Unidad {b}**")
                    c2.metric("KM", f"{lat['km_current']:,.0f}")
                    
                    if days >= 3: c1.error(f"⚠️ {days} días inactivo")
                    
                    if not maint.empty:
                        rem = maint.iloc[0]['km_next'] - lat['km_current']
                        if rem <= 500: c3.warning(f"🔧 Cambio próximo ({rem} km)")
                        else: c3.success("🟢 OK")

    elif choice == "⛽ Combustible":
        st.subheader("Carga Combustible")
        with st.form("f"):
            k = st.number_input("KM"); g = st.number_input("Galones"); c = st.number_input("Costo $")
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": "Combustible", "km_current": k, "gallons": g, "com_cost": c, "com_paid": c
                })
                st.success("Ok"); st.rerun()

    # --- CERRAR SESIÓN ---
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 CERRAR SESIÓN"):
        st.session_state.clear(); st.query_params.clear(); st.rerun()
