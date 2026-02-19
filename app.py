import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import FailedPrecondition
import google.generativeai as genai
import plotly.express as px  # Librería para gráficos visuales
import time
import urllib.parse

# --- 1. CONFIGURACIÓN Y ESTILOS ---
APP_CONFIG = {
    "APP_ID": "itero-titanium-v15",
    "MASTER_KEY": "ADMIN123",
    "VERSION": "8.5.0 Holística y Segura",
    "LOGO_URL": "Gemini_Generated_Image_buyjdmbuyjdmbuyj.png", # Tu logo
    "BOSS_PHONE": "0999999999" # <--- CAMBIA ESTO POR EL NÚMERO DEL JEFE
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

# --- UTILERÍAS ---
def format_phone(phone):
    """Convierte cualquier número al formato de WhatsApp (+593 automático)"""
    if not phone: return ""
    p = str(phone).replace(" ", "").replace("+", "").replace("-", "")
    if p.startswith("0"): return "593" + p[1:]  
    if not p.startswith("593"): return "593" + p 
    return p

# --- 2. CONFIGURACIÓN DE IA (GEMINI) ---
try:
    if "GEMINI_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_KEY"]["api_key"])
        HAS_AI = True
    else:
        HAS_AI = False
except Exception as e:
    HAS_AI = False
    st.error(f"Error configurando IA: {e}")

# --- 3. CAPA DE DATOS (BACKEND BLINDADO) ---
@st.cache_resource
def get_db_client():
    try:
        if not firebase_admin._apps:
            if "FIREBASE_JSON" in st.secrets:
                key_dict = dict(st.secrets["FIREBASE_JSON"])
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            else:
                return None
        return firestore.client()
    except Exception as e:
        st.error(f"Error de conexión DB: {e}")
        return None

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
    """IA Holística: Analiza mantenimientos, combustible y costos juntos."""
    if not HAS_AI: return "⚠️ IA no disponible (Revisa los Secretos)."
    
    try:
        cols = ['date', 'category', 'observations', 'km_current', 'gallons', 'mec_cost', 'com_cost']
        available_cols = [c for c in cols if c in df_bus.columns]
        summary = df_bus[available_cols].head(15).to_string()
        
        prompt = f"""
        Actúa como Jefe de Taller. Analiza TODO el historial del Bus {bus_id} (Mantenimientos, Combustible, Costos):
        {summary}
        
        Evalúa el conjunto. ¿Hay gastos excesivos en repuestos? ¿Consume mucho combustible? ¿Hay fallas repetitivas?
        Dame 3 puntos breves (Diagnóstico, Costos/Combustible, Recomendación). Usa emojis.
        """
    except Exception:
        return "Error al leer datos del bus."

    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not valid_models: return "⚠️ Error crítico: Sin modelos habilitados."

        chosen_model = valid_models[0]
        for m in valid_models:
            if "flash" in m: chosen_model = m; break
        if "flash" not in chosen_model:
            for m in valid_models:
                if "pro" in m: chosen_model = m; break

        model = genai.GenerativeModel(chosen_model)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error de conexión IA: {str(e)}"

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
            
            if st.button("INGRESAR", type="primary"):
                handle_login(f_in, u_in, r_in, pass_in)

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

def handle_login(f_in, u_in, r_in, pass_in):
    if not REFS: st.error("⚠️ Modo Offline"); return
    doc = REFS["fleets"].document(f_in).get()
    if not doc.exists: st.error("❌ Flota no encontrada."); return
    data = doc.to_dict()
    if data.get('status') == 'suspended': st.error("🚫 CUENTA SUSPENDIDA."); return

    access = False; role = ""; assigned_bus = "0"
    if "Adm" in r_in:
        if data.get('password') == pass_in: access = True; role = 'owner'
        else: st.error("🔒 Contraseña incorrecta.")
    else:
        # LOGIN CIEGO PARA CONDUCTOR (Seguridad)
        auth = REFS["fleets"].document(f_in).collection("authorized_users").document(u_in).get()
        if auth.exists and auth.to_dict().get('active', True): 
            access = True; role = 'driver'
            assigned_bus = auth.to_dict().get('bus', '0')
        else: st.error("❌ Usuario no autorizado.")

    if access:
        u_data = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': assigned_bus}
        st.session_state.user = u_data
        st.query_params.update({"f": f_in, "u": u_in, "r": role, "b": assigned_bus})
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
    if df.empty or 'bus' not in df.columns:
        st.info("⏳ Esperando datos... (Asegúrate de registrar información).")
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
            phone_jefe = format_phone(APP_CONFIG["BOSS_PHONE"])
            link = f"https://wa.me/{phone_jefe}?text={urllib.parse.quote(whatsapp_msg)}"
            st.markdown(f'''<a href="{link}" target="_blank">
                <button style="background-color:#25D366; color:white; border:none; padding:15px; width:100%; font-size:20px; font-weight:bold; border-radius:10px; cursor:pointer; margin-bottom:20px;">
                📲 NOTIFICAR AL JEFE
                </button></a>''', unsafe_allow_html=True)
        
        st.write("### 📜 Historial de mi Unidad")
        historial_mostrar = bus_df[['date', 'category', 'observations', 'km_current']].head(10).copy()
        historial_mostrar['date'] = historial_mostrar['date'].dt.strftime('%Y-%m-%d')
        st.dataframe(historial_mostrar, use_container_width=True, hide_index=True)
        return

    # --- VISTA DUEÑO (AGRUPADA POR BUS) ---
    st.write("Selecciona una unidad para ver su diagnóstico holístico.")
    for bus in buses:
        bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
        if bus_df.empty: continue
        
        latest = bus_df.iloc[0]
        color = "🟢"
        if not bus_df[bus_df['km_next'] > 0].empty:
            diff = bus_df[bus_df['km_next'] > 0].iloc[0]['km_next'] - latest['km_current']
            if diff < 0: color = "🔴"
            elif diff <= 500: color = "🟡"

        with st.expander(f"{color} BUS {bus} | KM Actual: {latest['km_current']:,.0f}", expanded=False):
            c1, c2 = st.columns([2,1])
            mostrar = bus_df[['date', 'category', 'km_current', 'mec_cost', 'com_cost']].head(3).copy()
            mostrar['date'] = mostrar['date'].dt.strftime('%Y-%m-%d')
            c1.dataframe(mostrar, use_container_width=True, hide_index=True)
            if c2.button(f"🤖 Diagnóstico IA", key=f"ai_{bus}"):
                with st.spinner("Analizando historial..."):
                    st.info(get_ai_analysis(bus_df, bus))

def render_reports(df):
    st.header("Reportes")
    if df.empty: st.warning("No hay datos."); return

    t1, t2, t3 = st.tabs(["📊 Gráficos Visuales", "🚦 Estado de Unidades", "📜 Base de Datos Cruda"])
    
    with t1:
        c1, c2 = st.columns(2)
        df['total_cost'] = df['mec_cost'] + df['com_cost']
        cost_by_cat = df.groupby('category')['total_cost'].sum().reset_index()
        if not cost_by_cat.empty:
            c1.plotly_chart(px.pie(cost_by_cat, values='total_cost', names='category', title='Gastos por Categoría', hole=0.4), use_container_width=True)
        cost_by_bus = df.groupby('bus')['total_cost'].sum().reset_index()
        if not cost_by_bus.empty:
            c2.plotly_chart(px.bar(cost_by_bus, x='bus', y='total_cost', title='Costos por Unidad'), use_container_width=True)

    with t2:
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        maint_view = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        report_data = []
        for _, r in maint_view.iterrows():
            ckm = last_km.get(r['bus'], 0); diff = r['km_next'] - ckm
            status = "🔴 VENCIDO" if diff < 0 else "🟡 PRÓXIMO" if diff <= 500 else "🟢 OK"
            report_data.append({"Bus": r['bus'], "Estado": status, "Item": r['category'], "KM Actual": ckm, "Meta": r['km_next'], "Restante": diff})
        rdf = pd.DataFrame(report_data).sort_values(by=['Bus'])
        if not rdf.empty:
            st.dataframe(rdf.style.map(lambda v: f'background-color: {"#ffcccc" if "VENCIDO" in v else "#fff3cd" if "PRÓXIMO" in v else "#d4edda"}', subset=['Estado']), use_container_width=True, hide_index=True)

    with t3:
        st.write("Historial completo. Puedes filtrar u ordenar por cualquier columna.")
        df_mostrar = df.copy()
        df_mostrar['date'] = df_mostrar['date'].dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(df_mostrar.sort_values('date', ascending=False), use_container_width=True, hide_index=True)

def render_accounting(df, user, phone_map):
    st.header("Cuentas por Pagar")
    if df.empty: return
    pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
    if pend.empty: st.success("🎉 Todo al día."); return

    # Agrupado por Bus
    for bus in sorted(pend['bus'].unique()):
        with st.expander(f"🚌 Deudas del Bus {bus}", expanded=True):
            deudas_bus = pend[pend['bus'] == bus]
            for _, r in deudas_bus.iterrows():
                st.write(f"**{r['category']}** ({r['date'].strftime('%d-%m-%Y')})")
                c1, c2 = st.columns(2)
                
                for prefix, cost, paid, name, lbl in [('m', 'mec_cost', 'mec_paid', 'mec_name', 'Mecánico'), ('c', 'com_cost', 'com_paid', 'com_name', 'Repuestos')]:
                    debt = r[cost] - r[paid]
                    col = c1 if prefix == 'm' else c2
                    if debt > 0:
                        col.metric(f"Deuda {lbl}", f"${debt:,.2f}", delta=-debt)
                        if user['role'] == 'owner':
                            val = col.number_input(f"Abono", key=f"{prefix}{r['id']}", max_value=float(debt))
                            if col.button(f"Pagar", key=f"b{prefix}{r['id']}") and REFS:
                                REFS["data"].collection("logs").document(r['id']).update({paid: firestore.Increment(val)})
                                ph = format_phone(phone_map.get(r.get(name), ''))
                                if ph:
                                    msg = f"Hola, te acabo de abonar ${val} por {r['category']} del Bus {bus}."
                                    col.markdown(f"[📲 Avisar por WhatsApp](https://wa.me/{ph}?text={urllib.parse.quote(msg)})")
                                fetch_fleet_data.clear() # Limpia caché al pagar
                                st.rerun()
                st.divider()

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
            fetch_fleet_data.clear()
            st.success("Guardado"); time.sleep(1); st.rerun()

def render_directory(providers, user):
    st.header("Proveedores")
    with st.expander("➕ Nuevo"):
        with st.form("np"):
            n = st.text_input("Nombre").upper(); p = st.text_input("WhatsApp (ej: 099...)"); t = st.selectbox("Tipo", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar") and REFS and n:
                REFS["data"].collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":user['fleet']})
                fetch_fleet_data.clear(); st.rerun()
    for p in providers:
        st.markdown(f"**{p['name']}** ({p['type']}) - {p.get('phone')}")

def render_fuel():
    user = st.session_state.user
    st.header("Combustible")
    with st.form("fuel"):
        k=st.number_input("KM Actual"); g=st.number_input("Galones"); c=st.number_input("Costo Total $")
        if st.form_submit_button("Guardar") and REFS:
            REFS["data"].collection("logs").add({"fleetId":user['fleet'],"bus":user['bus'],"date":datetime.now().isoformat(),"category":"Combustible","km_current":k,"gallons":g,"com_cost":c,"com_paid":c})
            fetch_fleet_data.clear()
            st.success("Ok"); st.rerun()

def render_personnel(user):
    st.header("Personal")
    with st.expander("➕ Agregar Conductor", expanded=False):
        with st.form("nd"):
            c1,c2,c3 = st.columns(3)
            nm=c1.text_input("Nombre").upper().strip()
            te=c2.text_input("Teléfono")
            bs=c3.text_input("Unidad Asignada")
            if st.form_submit_button("Guardar") and REFS and nm:
                REFS["fleets"].document(user['fleet']).collection("authorized_users").document(nm).set({"active":True,"phone":te,"bus":bs,"role":"driver"})
                st.rerun()
    if REFS:
        st.write("### Nómina")
        for us in REFS["fleets"].document(user['fleet']).collection("authorized_users").stream():
            d=us.to_dict()
            if d.get('role')!='admin':
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3,2,1])
                    status = "🟢" if d.get('active') else "🔴"
                    c1.markdown(f"**{us.id}** {status}<br><small>📞{d.get('phone','-')}</small>", unsafe_allow_html=True)
                    
                    # Edición de bus
                    new_bus = c2.text_input("Unidad Asignada", value=d.get('bus', ''), key=f"b_{us.id}")
                    if new_bus != d.get('bus', ''):
                        if c2.button("💾 Guardar Unidad", key=f"s_{us.id}"):
                            REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).update({"bus": new_bus}); st.rerun()

                    col_btn1, col_btn2 = c3.columns(2)
                    if col_btn1.button("🔒", key=f"lk_{us.id}"):
                        REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).update({"active":not d.get('active')}); st.rerun()
                    if col_btn2.button("🗑️", key=f"dl_{us.id}"):
                        REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).delete(); st.rerun()

def render_fleet_management(df, user):
    st.header("🚛 Gestión de Flota")
    if df.empty or 'bus' not in df.columns: st.warning("No hay unidades registradas."); return
    
    buses = sorted(df['bus'].unique())
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.subheader("✏️ Renombrar Unidad")
        old_bus = st.selectbox("Unidad a renombrar", buses, key="ren_old")
        new_bus = st.text_input("Nuevo número/nombre", key="ren_new")
        if st.button("Actualizar Historial") and new_bus and REFS:
            docs = REFS["data"].collection("logs").where("fleetId", "==", user['fleet']).where("bus", "==", old_bus).stream()
            for doc in docs: REFS["data"].collection("logs").document(doc.id).update({"bus": new_bus})
            users = REFS["fleets"].document(user['fleet']).collection("authorized_users").where("bus", "==", old_bus).stream()
            for u in users: REFS["fleets"].document(user['fleet']).collection("authorized_users").document(u.id).update({"bus": new_bus})
            fetch_fleet_data.clear()
            st.success("Unidad actualizada con éxito."); time.sleep(1); st.rerun()

    with c2.container(border=True):
        st.subheader("🗑️ Eliminar Unidad")
        del_bus = st.selectbox("Unidad a eliminar", buses, key="del_bus")
        st.error("⚠️ Esto borrará TODO el historial de la unidad.")
        if st.button("Eliminar Permanentemente") and REFS:
            docs = REFS["data"].collection("logs").where("fleetId", "==", user['fleet']).where("bus", "==", del_bus).stream()
            for doc in docs: REFS["data"].collection("logs").document(doc.id).delete()
            fetch_fleet_data.clear()
            st.success("Unidad eliminada."); time.sleep(1); st.rerun()

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
        
        # LOGO en la Barra Lateral
        if "LOGO_URL" in APP_CONFIG: 
            st.sidebar.image(APP_CONFIG["LOGO_URL"], width=200)
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

        # Menú Dinámico
        menu = {
            "🏠 Radar": lambda: render_radar(df, user),
            "⛽ Combustible": render_fuel,
            "📊 Reportes": lambda: render_reports(df),
            "🛠️ Taller": lambda: render_workshop(user, providers),
            "💰 Contabilidad": lambda: render_accounting(df, user, phone_map),
            "🏢 Directorio": lambda: render_directory(providers, user)
        }
        if user['role']=='owner': 
            menu["👥 Personal"] = lambda: render_personnel(user)
            menu["🚛 Gestión de Flota"] = lambda: render_fleet_management(df, user)
        
        choice = st.sidebar.radio("Ir a:", list(menu.keys()))
        st.divider()
        menu[choice]()
        
        # Botón de Respaldo CSV (MANTENIDO)
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.sidebar.download_button("📥 Descargar CSV", csv, f"itaro_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
        
        st.sidebar.markdown("---")
        if st.sidebar.button("🚪 Salir"):
            st.session_state.clear(); st.query_params.clear(); st.rerun()

if __name__ == "__main__":
    main()
