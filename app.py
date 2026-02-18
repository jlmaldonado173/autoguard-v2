import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import FailedPrecondition
import google.generativeai as genai
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y ESTILOS ---
APP_CONFIG = {
    "APP_ID": "itero-titanium-v15",
    "MASTER_KEY": "ADMIN123",
    "VERSION": "5.0.0 Stable"
}

UI_COLORS = {
    "primary": "#1E1E1E",
    "danger": "#FF4B4B",
    "success": "#28a745",
    "warning": "#ffc107",
    "bg_metric": "#f8f9fa"
}

st.set_page_config(page_title="Itaro AI", layout="wide", page_icon="🚛")

# Estilos CSS Profesionales
st.markdown(f"""
    <style>
    .main-title {{ font-size: 60px; font-weight: 800; color: {UI_COLORS['primary']}; text-align: center; margin-top: -20px; }}
    .stButton>button {{ width: 100%; border-radius: 8px; font-weight: bold; border: 1px solid #ddd; }}
    div[data-testid="stSidebar"] .stButton:last-child button {{
        background-color: {UI_COLORS['danger']}; color: white; border: none;
    }}
    .metric-box {{
        background-color: {UI_COLORS['bg_metric']}; border-left: 5px solid {UI_COLORS['primary']}; 
        padding: 15px; border-radius: 5px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    /* Estilo Tarjeta Conductor */
    .driver-card {{
        padding: 20px; border-radius: 15px; color: white; text-align: center; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONFIGURACIÓN DE IA (GEMINI) ---
try:
    if "GEMINI_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_KEY"]["api_key"])
        HAS_AI = True
    else:
        HAS_AI = False
        # No mostramos error, solo desactivamos la IA silenciosamente
except Exception as e:
    HAS_AI = False
    st.error(f"Error configurando IA: {e}")

# --- 3. CAPA DE DATOS (BACKEND BLINDADO) ---

@st.cache_resource
def get_db_client():
    try:
        # Evitamos inicializar dos veces
        if not firebase_admin._apps:
            if "FIREBASE_JSON" in st.secrets:
                # CORRECCIÓN: Usamos dict() para leer los secretos correctamente
                key_dict = dict(st.secrets["FIREBASE_JSON"])
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            else:
                return None
        return firestore.client()
    except Exception as e:
        st.error(f"Error de conexión DB: {e}")
        return None

# Inicializamos la DB aquí para que esté disponible globalmente
db = get_db_client()

def get_refs():
    if db:
        return {
            "fleets": db.collection("artifacts").document(APP_CONFIG["APP_ID"]).collection("registered_fleets"),
            "data": db.collection("artifacts").document(APP_CONFIG["APP_ID"]).collection("public").document("data")
        }
    return None

REFS = get_refs()

# --- FUNCIONES DE IA Y DATOS ---

def get_ai_analysis(df_bus, bus_id):
    """Analiza el historial del bus usando Google Gemini."""
    if not HAS_AI: return "⚠️ IA no disponible (Configura el Secreto GEMINI_KEY)."
    
    try:
        # Resumen para ahorrar tokens
        summary = df_bus[['date', 'category', 'observations', 'km_current', 'mec_cost', 'com_cost']].head(15).to_string()
        
        prompt = f"""
        Eres 'Itaro Copilot', un ingeniero mecánico experto y auditor.
        Analiza estos registros recientes del BUS {bus_id}:
        {summary}
        
        Tu tarea:
        1. Identifica patrones de fallo.
        2. Detecta costos sospechosos.
        3. Da una recomendación técnica corta.
        
        Responde en 3 puntos breves con emojis.
        """
        
        # CORRECCIÓN: Usamos el modelo más nuevo disponible
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error consultando al oráculo digital: {str(e)}"

@st.cache_data(ttl=300)
def fetch_fleet_data(fleet_id: str, role: str, bus_id: str, start_d: date, end_d: date):
    if not REFS: return [], pd.DataFrame()
    
    try:
        p_docs = REFS["data"].collection("providers").where("fleetId", "==", fleet_id).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        
        dt_start = datetime.combine(start_d, datetime.min.time())
        dt_end = datetime.combine(end_d, datetime.max.time())

        base_query = REFS["data"].collection("logs").where("fleetId", "==", fleet_id)
        if role == 'driver': base_query = base_query.where("bus", "==", bus_id)
            
        query = base_query.where("date", ">=", dt_start.isoformat()).where("date", "<=", dt_end.isoformat())
        
        try:
            logs = [l.to_dict() | {"id": l.id} for l in query.stream()]
        except FailedPrecondition as e:
            if "query requires an index" in str(e):
                url = str(e).split("here: ")[1].split(" ")[0] if "here: " in str(e) else ""
                st.error("⚠️ SISTEMA: Se requiere optimización de base de datos.")
                if url: st.markdown(f"[👉 ACTIVAR ÍNDICE DE RENDIMIENTO]({url})")
                return provs, pd.DataFrame()
            else: raise e

        cols_config = {
            'bus': '0', 'category': '', 'observations': '', 
            'km_current': 0, 'km_next': 0, 'mec_cost': 0, 
            'com_cost': 0, 'mec_paid': 0, 'com_paid': 0, 'gallons': 0
        }
        
        if not logs: return provs, pd.DataFrame(columns=list(cols_config.keys()) + ['date'])
        
        df = pd.DataFrame(logs)
        for col, val in cols_config.items():
            if col not in df.columns: df[col] = val
            if isinstance(val, (int, float)): df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return [], pd.DataFrame()

# --- 4. UI LOGIN Y REGISTRO ---

def ui_render_login():
    st.markdown('<div class="main-title">Itaro AI</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["👤 Ingresar", "📝 Crear Flota", "⚙️ Super Admin"])

    with t1:
        with st.container(border=True):
            col1, col2 = st.columns(2)
            f_in = col1.text_input("Código de Flota").upper().strip()
            u_in = col2.text_input("Usuario").upper().strip()
            r_in = st.selectbox("Perfil", ["Conductor", "Administrador/Dueño"])
            pass_in = st.text_input("Contraseña", type="password") if "Adm" in r_in else ""
            b_in = st.text_input("Unidad (Solo Conductores)") if "Cond" in r_in else "0"
            
            if st.button("INGRESAR", type="primary"):
                handle_login(f_in, u_in, r_in, pass_in, b_in)

    with t2:
        with st.container(border=True):
            nid = st.text_input("Crear Código Nuevo").upper().strip()
            own = st.text_input("Nombre Dueño").upper().strip()
            pas = st.text_input("Crear Contraseña", type="password")
            if st.button("REGISTRAR EMPRESA"):
                handle_register(nid, own, pas)

    with t3:
        if st.text_input("Master Key", type="password") == APP_CONFIG["MASTER_KEY"]:
            render_super_admin()

def handle_login(f_in, u_in, r_in, pass_in, b_in):
    if not REFS: st.error("⚠️ Modo Offline"); return
    doc = REFS["fleets"].document(f_in).get()
    if not doc.exists: st.error("❌ Flota no encontrada."); return
    data = doc.to_dict()
    if data.get('status') == 'suspended': st.error("🚫 CUENTA SUSPENDIDA."); return

    access = False; role = ""
    if "Adm" in r_in:
        if data.get('password') == pass_in: access = True; role = 'owner'
        else: st.error("🔒 Contraseña incorrecta.")
    else:
        auth = REFS["fleets"].document(f_in).collection("authorized_users").document(u_in).get()
        if auth.exists and auth.to_dict().get('active', True): access = True; role = 'driver'
        else: st.error("❌ Usuario no autorizado.")

    if access:
        u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': b_in if b_in else "0"}
        st.session_state.user = u_data
        st.query_params.update({"f": f_in, "u": u_in, "r": role, "b": u_data['bus']})
        st.rerun()

def handle_register(nid, own, pas):
    if REFS and nid and own and pas:
        ref = REFS["fleets"].document(nid)
        if not ref.get().exists:
            ref.set({"owner": own, "status": "active", "password": pas, "created": datetime.now()})
            ref.collection("authorized_users").document(own).set({"active": True, "role": "admin"})
            st.success("✅ Empresa creada."); time.sleep(1); st.rerun()
        else: st.error("Código en uso.")

def render_super_admin():
    if not REFS: return
    for f in REFS["fleets"].stream():
        d = f.to_dict()
        with st.expander(f"🏢 {f.id} - {d.get('owner')}", expanded=False):
            c1, c2 = st.columns(2)
            is_active = d.get('status') == 'active'
            if c1.button("SUSPENDER" if is_active else "ACTIVAR", key=f"s_{f.id}"):
                REFS["fleets"].document(f.id).update({"status": "suspended" if is_active else "active"}); st.rerun()
            if c2.button("ELIMINAR DATOS", key=f"d_{f.id}"):
                REFS["fleets"].document(f.id).delete(); st.rerun()

# --- 5. VISTAS PRINCIPALES ---

def render_radar(df, user):
    st.subheader("📡 Centro de Control")
    
    # CORRECCIÓN ANTI-ERROR: Si no hay datos, mostramos aviso y salimos
    if df.empty or 'bus' not in df.columns:
        st.info("⏳ Esperando datos... (Si es tu primera vez, asegúrate de haber creado el índice en el enlace de arriba).")
        return

    buses = sorted(df['bus'].unique()) if user['role']=='owner' else [user['bus']]
    
    # --- VISTA CONDUCTOR ---
    if user['role'] == 'driver':
        bus = user['bus']
        bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
        
        if bus_df.empty: st.warning("Tu unidad no tiene historial reciente."); return
        
        latest = bus_df.iloc[0]
        pending = bus_df[bus_df['km_next'] > 0]
        
        alert_msg = "✅ UNIDAD OPERATIVA"; alert_color = "#28a745"; whatsapp_msg = ""
        
        if not pending.empty:
            next_maint = pending.iloc[0]
            diff = next_maint['km_next'] - latest['km_current']
            
            if diff < 0:
                alert_msg = f"🚨 VENCIDO: {next_maint['category']}"; alert_color = "#dc3545"
                whatsapp_msg = f"Hola Jefe, reporto que mi unidad {bus} tiene VENCIDO el mantenimiento de {next_maint['category']} hace {abs(diff)} km."
            elif diff <= 500:
                alert_msg = f"⚠️ PRÓXIMO: {next_maint['category']}"; alert_color = "#ffc107"
                whatsapp_msg = f"Hola Jefe, aviso que al Bus {bus} le toca {next_maint['category']} en {diff} km."

        st.markdown(f"""
        <div class="driver-card" style="background-color:{alert_color};">
            <h1 style="margin:0;">BUS {bus}</h1>
            <h3 style="margin:0;">{alert_msg}</h3>
            <p style="font-size: 50px; font-weight: 800; margin: 10px 0;">{latest['km_current']:,.0f} KM</p>
        </div>
        """, unsafe_allow_html=True)

        if whatsapp_msg:
            boss_phone = "593999999999" # Debería venir de la DB idealmente
            link = f"https://wa.me/{boss_phone}?text={urllib.parse.quote(whatsapp_msg)}"
            st.markdown(f'''<a href="{link}" target="_blank">
                <button style="background-color:#25D366; color:white; border:none; padding:15px; width:100%; font-size:20px; font-weight:bold; border-radius:10px; cursor:pointer; margin-bottom:20px;">
                📲 NOTIFICAR AL JEFE
                </button></a>''', unsafe_allow_html=True)
        
        if st.button("🤖 CONSULTAR A ITARO COPILOT"):
            with st.spinner("Analizando..."):
                analysis = get_ai_analysis(bus_df, bus)
                st.info(analysis)
        return

    # --- VISTA DUEÑO ---
    cols = st.columns(3)
    for i, bus in enumerate(buses):
        with cols[i % 3]:
            bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
            if bus_df.empty: continue
            
            latest = bus_df.iloc[0]
            status_color = "#28a745"; status_text = "OK"
            
            pending = bus_df[bus_df['km_next'] > 0]
            if not pending.empty:
                diff = pending.iloc[0]['km_next'] - latest['km_current']
                if diff < 0: status_color = "#dc3545"; status_text = "VENCIDO"
                elif diff <= 500: status_color = "#ffc107"; status_text = "PRÓXIMO"

            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                c1.markdown(f"### Bus {bus}")
                c2.markdown(f"<span style='color:{status_color}; font-weight:bold'>{status_text}</span>", unsafe_allow_html=True)
                st.caption(f"KM: {latest['km_current']:,.0f}")
                
                if st.button(f"🤖 IA", key=f"ai_{bus}"):
                     with st.spinner("Consultando..."):
                        res = get_ai_analysis(bus_df, bus)
                        st.info(res)

def render_reports(df):
    st.header("Reportes")
    if df.empty: st.warning("No hay datos."); return

    t1, t2 = st.tabs(["🚦 Estado Actual", "📜 Historial"])
    
    with t1:
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        maint_view = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        
        report_data = []
        for _, r in maint_view.iterrows():
            ckm = last_km.get(r['bus'], 0)
            diff = r['km_next'] - ckm
            status = "🔴 VENCIDO" if diff < 0 else "🟡 PRÓXIMO" if diff <= 500 else "🟢 OK"
            report_data.append({"Estado": status, "Bus": r['bus'], "Item": r['category'], "KM Actual": ckm, "Meta": r['km_next'], "Restante": diff})
            
        rdf = pd.DataFrame(report_data)
        if not rdf.empty:
            def color_status(val):
                color = '#ffcccc' if 'VENCIDO' in val else '#fff3cd' if 'PRÓXIMO' in val else '#d4edda'
                return f'background-color: {color}; color: black; font-weight: bold'
            st.dataframe(rdf.style.map(color_status, subset=['Estado']), use_container_width=True)

    with t2:
        c1, c2 = st.columns(2)
        sel_bus = c1.selectbox("Bus", ["Todas"] + sorted(df['bus'].unique().tolist()))
        sel_cat = c2.selectbox("Categoría", ["Todas"] + sorted(df['category'].unique().tolist()))
        
        df_fil = df.copy()
        if sel_bus != "Todas": df_fil = df_fil[df_fil['bus'] == sel_bus]
        if sel_cat != "Todas": df_fil = df_fil[df_fil['category'] == sel_cat]
        
        m1, m2 = st.columns(2)
        total = df_fil['mec_cost'].sum() + df_fil['com_cost'].sum()
        m1.metric("Gasto Total", f"${total:,.2f}")
        st.dataframe(df_fil[['date', 'bus', 'category', 'observations', 'mec_cost', 'com_cost']].sort_values('date', ascending=False), use_container_width=True, hide_index=True)

def render_accounting(df, user, phone_map):
    st.header("Cuentas por Pagar")
    if df.empty: return

    pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
    if pend.empty: st.success("🎉 Todo al día."); return

    for _, r in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"{r['category']} - Bus {r['bus']}")
            c1, c2 = st.columns(2)
            
            def pay_widget(col, prefix, cost, paid, name, label):
                debt = r[cost] - r[paid]
                if debt > 0:
                    col.metric(f"Deuda {label}", f"${debt:,.2f}", delta=-debt)
                    if user['role'] == 'owner':
                        val = col.number_input(f"Abono", key=f"{prefix}{r['id']}", max_value=float(debt))
                        if col.button(f"Pagar", key=f"b{prefix}{r['id']}") and REFS:
                            REFS["data"].collection("logs").document(r['id']).update({paid: firestore.Increment(val)})
                            ph = phone_map.get(r.get(name), '').replace('+','').strip()
                            if ph:
                                msg = f"Pago ${val} - {label} ({r['category']})"
                                col.markdown(f"[📲 WhatsApp](https://wa.me/{ph}?text={urllib.parse.quote(msg)})")
                            st.rerun()

            pay_widget(c1, "m", "mec_cost", "mec_paid", "mec_name", "Mecánico")
            pay_widget(c2, "c", "com_cost", "com_paid", "com_name", "Repuestos")

def render_workshop(user, providers):
    st.header("Taller")
    mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    with st.form("workshop"):
        tp = st.radio("Tipo", ["Preventivo", "Correctivo"], horizontal=True)
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Carrocería", "Vidrios", "Otro"])
        obs = st.text_area("Detalle")
        ka = c1.number_input("KM Actual", min_value=0)
        kn = c2.number_input("Próximo Cambio", min_value=ka) if tp == "Preventivo" else 0
        
        st.divider()
        c3, c4 = st.columns(2)
        mn = c3.selectbox("Mecánico", ["N/A"] + mecs); mc = c3.number_input("Costo M.O.", min_value=0.0); mp = c3.number_input("Abono M.O.", min_value=0.0)
        rn = c4.selectbox("Repuestos", ["N/A"] + coms); rc = c4.number_input("Costo Rep.", min_value=0.0); rp = c4.number_input("Abono Rep.", min_value=0.0)
        
        if st.form_submit_button("GUARDAR", type="primary") and REFS:
            REFS["data"].collection("logs").add({
                "fleetId": user['fleet'], "bus": user['bus'], "date": datetime.now().isoformat(),
                "category": cat, "observations": obs, "km_current": ka, "km_next": kn,
                "mec_name": mn, "mec_cost": mc, "mec_paid": mp, 
                "com_name": rn, "com_cost": rc, "com_paid": rp
            })
            st.success("Guardado"); time.sleep(1); st.rerun()

def render_directory(providers, user):
    st.header("Proveedores")
    with st.expander("➕ Nuevo"):
        with st.form("np"):
            n = st.text_input("Nombre").upper(); p = st.text_input("WhatsApp"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar") and REFS and n:
                REFS["data"].collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":user['fleet']}); st.rerun()
    for p in providers:
        st.markdown(f"**{p['name']}** ({p['type']}) - {p.get('phone')}")

def render_fuel():
    user = st.session_state.user
    st.header("Combustible")
    with st.form("fuel"):
        k=st.number_input("KM"); g=st.number_input("Gal"); c=st.number_input("$")
        if st.form_submit_button("Guardar") and REFS:
            REFS["data"].collection("logs").add({"fleetId":user['fleet'],"bus":user['bus'],"date":datetime.now().isoformat(),"category":"Combustible","km_current":k,"gallons":g,"com_cost":c,"com_paid":c})
            st.success("Ok"); st.rerun()

def render_personnel(user):
    st.header("Personal")
    with st.expander("➕ Agregar", expanded=False):
        with st.form("nd"):
            c1,c2,c3=st.columns(3)
            nm=c1.text_input("Nombre").upper().strip(); ce=c2.text_input("Cédula"); te=c3.text_input("Teléfono")
            if st.form_submit_button("Guardar") and REFS and nm:
                REFS["fleets"].document(user['fleet']).collection("authorized_users").document(nm).set({"active":True,"cedula":ce,"phone":te})
                st.rerun()
    if REFS:
        st.write("### Nómina")
        for us in REFS["fleets"].document(user['fleet']).collection("authorized_users").stream():
            d=us.to_dict()
            if d.get('role')!='admin':
                with st.container(border=True):
                    c1,c2,c3 = st.columns([3,1,1])
                    status = "🟢" if d.get('active') else "🔴"
                    c1.markdown(f"**{us.id}** {status}\n<small>🆔{d.get('cedula','-')} 📞{d.get('phone','-')}</small>", unsafe_allow_html=True)
                    if c2.button("🔒", key=f"lk_{us.id}"):
                        REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).update({"active":not d.get('active')}); st.rerun()
                    if c3.button("🗑️", key=f"dl_{us.id}"):
                        REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).delete(); st.rerun()

# --- 6. PROGRAMA PRINCIPAL ---
def main():
    if 'user' not in st.session_state:
        params = st.query_params
        if "f" in params:
            st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b", "0")}
            st.rerun()
        else:
            ui_render_login()
    else:
        user = st.session_state.user
        st.sidebar.title("Itaro AI")
        st.sidebar.caption(f"{user['name']} ({user['role']})")
        
        # Filtro Global de Fechas
        d_end = datetime.now().date()
        d_start = d_end - timedelta(days=90)
        dr = st.sidebar.date_input("Fecha:", [d_start, d_end])
        s, e = dr if isinstance(dr, tuple) and len(dr)==2 else (d_start, d_end)
        
        # Carga de datos
        providers, df = fetch_fleet_data(user['fleet'], user['role'], user['bus'], s, e)
        phone_map = {p['name']: p.get('phone', '') for p in providers}

        # Alertas Sidebar
        if not df.empty and 'bus' in df.columns:
            last_km = df.sort_values('date').groupby('bus')['km_current'].last()
            pending = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
            urg = sum(1 for _, r in pending.iterrows() if r['km_next'] - last_km.get(r['bus'],0) < 0)
            if urg > 0: st.sidebar.error(f"🚨 {urg} VENCIDOS")

        # Menú
        menu = {
            "🏠 Radar": lambda: render_radar(df, user),
            "⛽ Combustible": render_fuel,
            "📊 Reportes": lambda: render_reports(df),
            "🛠️ Taller": lambda: render_workshop(user, providers),
            "💰 Contabilidad": lambda: render_accounting(df, user, phone_map),
            "🏢 Directorio": lambda: render_directory(providers, user)
        }
        if user['role']=='owner': menu["👥 Personal"] = lambda: render_personnel(user)
        
        choice = st.sidebar.radio("Ir a:", list(menu.keys()))
        st.divider()
        menu[choice]()
        
        # Botón de Respaldo CSV
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.sidebar.download_button("📥 Bajar CSV", csv, f"itaro_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
        
        st.sidebar.markdown("---")
        if st.sidebar.button("🚪 Salir"):
            st.session_state.clear(); st.query_params.clear(); st.rerun()

if __name__ == "__main__":
    main()
