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

st.markdown("""
    <style>
    /* Título Principal */
    .main-title { font-size: 60px; font-weight: 800; color: #1E1E1E; text-align: center; margin-top: -20px; }
    
    /* Botones Generales */
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }
    
    /* Botón Rojo (Logout/Eliminar) */
    div[data-testid="stSidebar"] .stButton:last-child button {
        background-color: #FF4B4B; color: white; border: none;
    }
    
    /* Cajas de Métricas en Reportes */
    .metric-box {
        background-color: #f0f2f6; border-left: 5px solid #1E1E1E; padding: 15px; border-radius: 5px; margin-bottom: 10px;
    }
    
    /* Estados Visuales */
    .status-ok { color: green; font-weight: bold; }
    .status-warn { color: orange; font-weight: bold; }
    .status-err { color: red; font-weight: bold; }
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
        return None # Modo Offline silencioso

db = init_db()
APP_ID = "itero-titanium-v15"
MASTER_KEY = "ADMIN123" # Clave del dueño del software

if db:
    FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
    DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 3. GESTIÓN DE SESIÓN ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b", "0")
        }
        st.rerun()

# --- 4. ACCESO (LOGIN / REGISTRO / SUPER ADMIN) ---
if 'user' not in st.session_state:
    st.markdown('<div class="main-title">Itaro</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["👤 Ingresar", "📝 Crear Flota", "⚙️ Super Admin"])

    with t1: # LOGIN SEGURO
        with st.container(border=True):
            f_in = st.text_input("Código de Flota").upper().strip()
            u_in = st.text_input("Usuario").upper().strip()
            r_in = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            
            # Contraseña solo para Admin
            pass_in = ""
            if "Adm" in r_in:
                pass_in = st.text_input("Contraseña", type="password")
            
            b_in = st.text_input("Unidad (Solo Conductores)")
            
            if st.button("INGRESAR"):
                if db:
                    doc = FLEETS_REF.document(f_in).get()
                    if doc.exists:
                        data = doc.to_dict()
                        if data.get('status') == 'suspended':
                            st.error("🚫 CUENTA SUSPENDIDA POR EL PROVEEDOR.")
                        else:
                            access = False; role = ""
                            
                            # Validación Admin (Password)
                            if "Adm" in r_in:
                                if data.get('password') == pass_in:
                                    access = True; role = 'owner'
                                else: st.error("🔒 Contraseña incorrecta.")
                            
                            # Validación Conductor (Whitelist)
                            else:
                                auth = FLEETS_REF.document(f_in).collection("authorized_users").document(u_in).get()
                                if auth.exists and auth.to_dict().get('active', True):
                                    access = True; role = 'driver'
                                else: st.error("❌ Usuario no autorizado.")

                            if access:
                                u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': b_in if b_in else "0"}
                                st.session_state.user = u_data
                                st.query_params.update({"f":f_in, "u":u_in, "r":role, "b":u_data['bus']})
                                st.rerun()
                    else: st.error("❌ Flota no encontrada.")
                else: st.error("⚠️ Sin conexión a internet.")

    with t2: # REGISTRO
        with st.container(border=True):
            st.info("Cree su empresa y proteja su acceso.")
            nid = st.text_input("Crear Código").upper().strip()
            own = st.text_input("Nombre Dueño").upper().strip()
            pas = st.text_input("Crear Contraseña", type="password")
            if st.button("REGISTRAR EMPRESA"):
                if db and nid and own and pas:
                    ref = FLEETS_REF.document(nid)
                    if not ref.get().exists:
                        ref.set({"owner": own, "status": "active", "password": pas, "created": datetime.now()})
                        ref.collection("authorized_users").document(own).set({"active": True, "role": "admin"})
                        st.success("✅ Empresa creada."); time.sleep(1); st.rerun()
                    else: st.error("Código en uso.")

    with t3: # MODO DIOS
        if st.text_input("Master Key", type="password") == MASTER_KEY and db:
            for f in FLEETS_REF.stream():
                d = f.to_dict()
                c1,c2,c3 = st.columns([3,1,1])
                c1.write(f"🏢 {f.id} ({d.get('status')})")
                
                btn_txt = "SUSPENDER" if d.get('status')=='active' else "ACTIVAR"
                if c2.button(btn_txt, key=f"s_{f.id}"):
                    ns = "suspended" if d.get('status')=='active' else 'active'
                    FLEETS_REF.document(f.id).update({"status": ns}); st.rerun()
                    
                if c3.button("DEL", key=f"d_{f.id}"):
                    FLEETS_REF.document(f.id).delete(); st.rerun()

# --- 5. SISTEMA OPERATIVO ---
else:
    u = st.session_state.user
    
    # -------------------------------------------------------------
    # --- FUNCIÓN DE CARGA BLINDADA (CORREGIDA) ---
    # -------------------------------------------------------------
    def load_data():
        if not db: return [], pd.DataFrame()
        try:
            # 1. Cargar Proveedores
            p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
            provs = [p.to_dict() | {"id": p.id} for p in p_docs]
            
            # 2. Cargar Logs
            q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
            if u['role'] == 'driver': 
                q = q.where("bus", "==", u['bus'])
            logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
            
            # 3. Columnas obligatorias
            cols = ['bus', 'category', 'observations', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'gallons']
            
            if not logs:
                return provs, pd.DataFrame(columns=cols)
            
            df = pd.DataFrame(logs)
            
            # 4. Rellenar faltantes
            for c in cols: 
                if c not in df.columns: 
                    df[c] = "" if c == 'observations' else 0 
            
            # 5. Convertir a números
            for nc in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'gallons']:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0)
            
            # 6. Convertir fecha
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            return provs, df
        except: 
            return [], pd.DataFrame()
    # -------------------------------------------------------------

    providers, df = load_data()
    # Mapa de teléfonos para WhatsApp
    phone_map = {p['name']: p.get('phone', '') for p in providers}

    # --- CÁLCULO DE ALERTAS GLOBALES ---
    urgent = 0; warning = 0
    if not df.empty:
        # Lógica: Último KM reportado vs Mantenimientos pendientes
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        # Filtramos solo preventivos (km_next > 0)
        maint_view = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        for _, row in maint_view.iterrows():
            ckm = last_km.get(row['bus'], 0)
            diff = row['km_next'] - ckm
            if diff < 0: urgent += 1
            elif diff <= 500: warning += 1

    # Sidebar Header
    st.sidebar.markdown("<h1 style='text-align: center;'>Itaro</h1>", unsafe_allow_html=True)
    st.sidebar.caption(f"Usuario: {u['name']}")

    # ALERTAS VISUALES ARRIBA DE TODO
    if urgent > 0: st.error(f"🚨 ALERTA CRÍTICA: Tienes {urgent} mantenimientos VENCIDOS. Revisa 'Reportes'.")
    elif warning > 0: st.warning(f"⚠️ AVISO: Tienes {warning} mantenimientos próximos.")

    # Botón Respaldo
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Respaldo", csv, "itaro_backup.csv", "text/csv")

    menu = ["⛽ Combustible", "🏠 Radar", "📊 Reportes", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
    if u['role'] == 'owner': menu.append("👥 Personal")
    choice = st.sidebar.radio("Navegación", menu)

    # --- 1. PERSONAL (COMPLETO CON CÉDULA/TEL) ---
    if choice == "👥 Personal":
        st.header("Gestión de Personal")
        with st.expander("➕ Agregar Conductor", expanded=True):
            with st.form("nd"):
                c1,c2,c3 = st.columns(3)
                nm = c1.text_input("Nombre").upper().strip()
                ce = c2.text_input("Cédula"); te = c3.text_input("Teléfono")
                if st.form_submit_button("Guardar") and db and nm:
                    FLEETS_REF.document(u['fleet']).collection("authorized_users").document(nm).set({"active":True,"cedula":ce,"phone":te,"date":datetime.now().isoformat()})
                    st.success("Guardado"); st.rerun()
        
        if db:
            st.write("### Nómina Activa")
            for us in FLEETS_REF.document(u['fleet']).collection("authorized_users").stream():
                d = us.to_dict()
                if d.get('role') != 'admin':
                    with st.container(border=True):
                        c1,c2,c3,c4 = st.columns([3, 1, 1, 1])
                        st_icon = "🟢" if d.get('active') else "🔴"
                        c1.write(f"**{us.id}**\n🆔{d.get('cedula','-')} 📞{d.get('phone','-')}")
                        c2.write(st_icon)
                        if c3.button("🔒", key=f"s{us.id}"): 
                            FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).update({"active": not d.get('active')}); st.rerun()
                        if c4.button("🗑️", key=f"d{us.id}"):
                             FLEETS_REF.document(u['fleet']).collection("authorized_users").document(us.id).delete(); st.rerun()

    # --- 2. REPORTES (FILTRO JERÁRQUICO) ---
    elif choice == "📊 Reportes":
        st.header("Reportes de Flota")
        
        tab1, tab2 = st.tabs(["🚦 Semáforo", "📜 Historial Detallado"])
        
        # TAB 1: Semáforo
        with tab1:
            if not df.empty:
                last_km = df.sort_values('date').groupby('bus')['km_current'].last()
                mview = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category']).copy()
                rep = []
                for _, r in mview.iterrows():
                    ckm = last_km.get(r['bus'], 0)
                    dff = r['km_next'] - ckm
                    stt = "🔴 VENCIDO" if dff < 0 else "🟡 PRÓXIMO" if dff <= 500 else "🟢 OK"
                    rep.append({"Estado": stt, "Bus": r['bus'], "Item": r['category'], "KM Actual": ckm, "Meta": r['km_next']})
                
                if not rep:
                    # Crear DF vacío con columnas para evitar error
                    rdf = pd.DataFrame(columns=["Estado", "Bus", "Item", "KM Actual", "Meta"])
                else:
                    rdf = pd.DataFrame(rep)

                fil = st.radio("Filtro Rápido:", ["Todos", "🔴 Vencidos", "🟡 Próximos"], horizontal=True)
                
                if not rdf.empty:
                    if fil == "🔴 Vencidos": rdf = rdf[rdf['Estado']=="🔴 VENCIDO"]
                    if fil == "🟡 Próximos": rdf = rdf[rdf['Estado']=="🟡 PRÓXIMO"]
                
                st.dataframe(rdf, hide_index=True, use_container_width=True)
            else: st.info("Sin datos.")

        # TAB 2: Historial Filtrado
        with tab2:
            if df.empty:
                st.info("Sin registros.")
            else:
                c1, c2 = st.columns(2)
                # Filtros
                unidades = ["Todas"] + sorted(df['bus'].unique().tolist())
                sel_bus = c1.selectbox("1. Unidad", unidades)
                
                categorias = ["Todas"] + sorted(df['category'].unique().tolist())
                sel_cat = c2.selectbox("2. Categoría", categorias)
                
                # Aplicar
                df_fil = df.copy()
                if sel_bus != "Todas": df_fil = df_fil[df_fil['bus'] == sel_bus]
                if sel_cat != "Todas": df_fil = df_fil[df_fil['category'] == sel_cat]
                
                st.divider()
                
                if not df_fil.empty:
                    # Métricas
                    total = df_fil['mec_cost'].sum() + df_fil['com_cost'].sum()
                    st.markdown(f"<div class='metric-box'>💰 Gasto Total Selección: <b>${total:,.2f}</b></div>", unsafe_allow_html=True)
                    st.write("")
                    st.dataframe(df_fil[['date', 'bus', 'category', 'observations', 'km_current', 'mec_cost', 'com_cost']].sort_values('date', ascending=False), hide_index=True, use_container_width=True)
                else: st.warning("No hay registros con esos filtros.")

    # --- 3. CONTABILIDAD (WHATSAPP) ---
    elif choice == "💰 Contabilidad":
        st.header("Cuentas por Pagar")
        if u['role'] == 'owner' and not df.empty:
            df['t'] = df['mec_cost'] + df['com_cost']
            st.bar_chart(df.groupby('bus')['t'].sum())

        pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
        if pend.empty: st.success("Todo pagado.")
        
        for _, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"**{r['category']}** (Bus {r['bus']})")
                c1, c2 = st.columns(2)
                
                dm = r['mec_cost'] - r['mec_paid']
                if dm > 0:
                    c1.error(f"🔧 Mecánico: ${dm:,.2f}")
                    if u['role'] == 'owner':
                        v = c1.number_input("Abono", key=f"m{r['id']}")
                        if c1.button("Pagar", key=f"bm{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"mec_paid": firestore.Increment(v)})
                            tel = phone_map.get(r.get('mec_name'), '')
                            msg = f"Abono ${v} - {r['category']}"
                            c1.markdown(f"[📱 Enviar Comprobante]({f'https://wa.me/{tel}?text={urllib.parse.quote(msg)}'})")

                dc = r['com_cost'] - r['com_paid']
                if dc > 0:
                    c2.warning(f"📦 Repuestos: ${dc:,.2f}")
                    if u['role'] == 'owner':
                        v = c2.number_input("Abono", key=f"c{r['id']}")
                        if c2.button("Pagar", key=f"bc{r['id']}") and db:
                            DATA_REF.collection("logs").document(r['id']).update({"com_paid": firestore.Increment(v)})
                            tel = phone_map.get(r.get('com_name'), '')
                            msg = f"Abono ${v} - Repuestos {r['category']}"
                            c2.markdown(f"[📱 Enviar Comprobante]({f'https://wa.me/{tel}?text={urllib.parse.quote(msg)}'})")

    # --- 4. TALLER (SINCRONIZADO + OBS) ---
    elif choice == "🛠️ Taller":
        st.header("Mantenimiento")
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("tf"):
            tp = st.radio("Tipo", ["Preventivo (Alerta)", "Correctivo"])
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Carrocería", "Vidrios", "Otro"])
            obs = c2.text_area("Observaciones")
            ka = c1.number_input("KM Actual", min_value=0)
            kn = 0
            if "Preventivo" in tp: kn = c2.number_input("Próximo Cambio", min_value=ka)
            
            st.divider()
            c3, c4 = st.columns(2)
            
            mn = c3.selectbox("Mecánico", ["N/A"] + mecs)
            mc = c3.number_input("Costo M.O. ($)", min_value=0.0)
            mp = c3.number_input("Abono Hoy M.O. ($)", min_value=0.0)
            
            rn = c4.selectbox("Comercio", ["N/A"] + coms)
            rc = c4.number_input("Costo Rep. ($)", min_value=0.0)
            cp = c4.number_input("Abono Hoy Rep. ($)", min_value=0.0)
            
            if st.form_submit_button("GUARDAR"):
                if mp > mc or cp > rc:
                    st.error("⚠️ Error: El abono no puede superar el costo.")
                elif db:
                    DATA_REF.collection("logs").add({
                        "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                        "category": cat, "observations": obs, 
                        "km_current": ka, "km_next": kn,
                        "mec_name": mn, "mec_cost": mc, "mec_paid": mp, 
                        "com_name": rn, "com_cost": rc, "com_paid": cp
                    })
                    st.success("Guardado."); time.sleep(1); st.rerun()
                else: st.error("Offline")

    # --- 5. DIRECTORIO (WHATSAPP) ---
    elif choice == "🏢 Directorio":
        st.header("Proveedores")
        with st.expander("➕ Nuevo"):
            with st.form("d"):
                n = st.text_input("Nombre").upper(); p = st.text_input("WhatsApp"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar") and db and n:
                    DATA_REF.collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":u['fleet']}); st.rerun()
        if providers:
            for p in providers:
                with st.container(border=True):
                    c1,c2=st.columns([3,1]); c1.write(f"**{p['name']}**\n{p.get('phone')}")
                    ph = p.get('phone', '').replace('+', '').strip()
                    if ph: c2.markdown(f'''<a href="https://wa.me/{ph}" target="_blank">WhatsApp</a>''', unsafe_allow_html=True)

    # --- 6. RADAR & GAS ---
    elif choice == "🏠 Radar":
        st.subheader("Radar de Flota")
        for b in sorted(df['bus'].unique()) if u['role']=='owner' else [u['bus']]:
            b_df = df[df['bus']==b].sort_values('date', ascending=False)
            if not b_df.empty:
                lat = b_df.iloc[0]
                d = (datetime.now()-lat['date']).days
                # Semáforo
                clr = "green"; msg = "OK"
                maint = b_df[b_df['km_next'] > 0]
                if not maint.empty:
                    diff = maint.iloc[0]['km_next'] - lat['km_current']
                    if diff < 0: clr = "red"; msg = "VENCIDO"
                    elif diff <= 500: clr = "orange"; msg = "PRÓXIMO"

                with st.container(border=True):
                    c1,c2,c3=st.columns(3)
                    c1.write(f"**Unidad {b}**")
                    c2.metric("KM", f"{lat['km_current']:,.0f}")
                    c3.markdown(f"<span style='color:{clr}; font-weight:bold'>{msg}</span>", unsafe_allow_html=True)
                    if d>=3: st.error(f"⚠️ {d} días inactivo")

    elif choice == "⛽ Combustible":
        with st.form("f"):
            k=st.number_input("KM"); g=st.number_input("Gal"); c=st.number_input("$")
            if st.form_submit_button("Guardar") and db:
                DATA_REF.collection("logs").add({"fleetId":u['fleet'],"bus":u['bus'],"date":datetime.now().isoformat(),"category":"Combustible","km_current":k,"gallons":g,"com_cost":c,"com_paid":c})
                st.success("Ok"); st.rerun()

    # --- LOGOUT ---
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.clear(); st.query_params.clear(); st.rerun()
