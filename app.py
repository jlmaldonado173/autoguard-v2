import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import FailedPrecondition
import json
import time
import urllib.parse

# --- 1. CONSTANTES Y CONFIGURACIÓN ---
APP_CONFIG = {
    "APP_ID": "itero-titanium-v15",
    "MASTER_KEY": "ADMIN123",
    "VERSION": "3.0.0 Scalable"
}

UI_COLORS = {
    "primary": "#1E1E1E",
    "danger": "#FF4B4B",
    "success": "#28a745",
    "warning": "#ffc107",
    "bg_metric": "#f8f9fa"
}

st.set_page_config(page_title="Itaro Pro", layout="wide", page_icon="🚛")

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
    /* Mejoras visuales para tablas */
    [data-testid="stDataFrame"] {{ border: 1px solid #eee; border-radius: 8px; overflow: hidden; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. CAPA DE DATOS (BACKEND) ---

@st.cache_resource
def get_db_client():
    try:
        if not firebase_admin._apps:
            if "FIREBASE_JSON" in st.secrets:
                cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
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

# --- FUNCIÓN DE CARGA NIVEL DIOS (PAGINADA/FILTRADA) ---
@st.cache_data(ttl=300) # Cache de 5 minutos
def fetch_fleet_data(fleet_id: str, role: str, bus_id: str, start_d: date, end_d: date):
    """
    Descarga datos optimizados por fecha.
    Maneja automáticamente la falta de índices en Firestore.
    """
    if not REFS: return [], pd.DataFrame()
    
    try:
        # 1. Proveedores (Siempre se cargan todos, son pocos)
        p_docs = REFS["data"].collection("providers").where("fleetId", "==", fleet_id).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        
        # 2. Construcción de Query de Logs con Fechas
        # Convertir date a datetime para Firestore
        dt_start = datetime.combine(start_d, datetime.min.time())
        dt_end = datetime.combine(end_d, datetime.max.time())

        base_query = REFS["data"].collection("logs").where("fleetId", "==", fleet_id)
        
        if role == 'driver': 
            base_query = base_query.where("bus", "==", bus_id)
            
        # Aplicamos filtro de fecha (Esto requiere índice compuesto en Firestore)
        query = base_query.where("date", ">=", dt_start.isoformat()).where("date", "<=", dt_end.isoformat())
        
        try:
            logs = [l.to_dict() | {"id": l.id} for l in query.stream()]
        except FailedPrecondition as e:
            # Captura mágica de error de índice
            if "query requires an index" in str(e):
                url = str(e).split("here: ")[1].split(" ")[0] if "here: " in str(e) else ""
                st.error("⚠️ RENDIMIENTO: Se requiere crear un índice en Firebase para optimizar esta consulta.")
                if url: st.markdown(f"[👉 CLIC AQUÍ PARA CREAR ÍNDICE AUTOMÁTICAMENTE]({url})")
                return provs, pd.DataFrame() # Retorna vacío hasta que se cree
            else:
                raise e

        # 3. Data Cleaning
        cols_config = {
            'bus': '0', 'category': '', 'observations': '', 
            'km_current': 0, 'km_next': 0, 'mec_cost': 0, 
            'com_cost': 0, 'mec_paid': 0, 'com_paid': 0, 'gallons': 0
        }
        
        if not logs:
            return provs, pd.DataFrame(columns=list(cols_config.keys()) + ['date'])
        
        df = pd.DataFrame(logs)
        
        for col, default_val in cols_config.items():
            if col not in df.columns:
                df[col] = default_val
            if isinstance(default_val, (int, float)):
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df
        
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return [], pd.DataFrame()

# --- 3. UI LOGIN Y REGISTRO ---

def ui_render_login():
    st.markdown('<div class="main-title">Itaro</div>', unsafe_allow_html=True)
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
            st.info("Cree su empresa y proteja su acceso.")
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
    if not doc.exists:
        st.error("❌ Flota no encontrada."); return

    data = doc.to_dict()
    if data.get('status') == 'suspended':
        st.error("🚫 CUENTA SUSPENDIDA."); return

    access = False; role = ""
    
    if "Adm" in r_in:
        if data.get('password') == pass_in:
            access = True; role = 'owner'
        else: st.error("🔒 Contraseña incorrecta.")
    else:
        auth = REFS["fleets"].document(f_in).collection("authorized_users").document(u_in).get()
        if auth.exists and auth.to_dict().get('active', True):
            access = True; role = 'driver'
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
    st.write("### Panel de Control")
    for f in REFS["fleets"].stream():
        d = f.to_dict()
        with st.expander(f"🏢 {f.id} - {d.get('owner')}", expanded=False):
            c1, c2 = st.columns(2)
            is_active = d.get('status') == 'active'
            if c1.button("SUSPENDER" if is_active else "ACTIVAR", key=f"s_{f.id}"):
                REFS["fleets"].document(f.id).update({"status": "suspended" if is_active else "active"})
                st.rerun()
            if c2.button("ELIMINAR DATOS", key=f"d_{f.id}"):
                REFS["fleets"].document(f.id).delete()
                st.rerun()

# --- 4. APLICACIÓN PRINCIPAL ---

def main_app():
    user = st.session_state.user
    
    # --- SIDEBAR MEJORADA ---
    st.sidebar.title("Itaro")
    st.sidebar.caption(f"Hola, {user['name']} ({user['role'].upper()})")
    
    # 🌟 FILTRO DE FECHAS (NUEVO)
    st.sidebar.markdown("### 📅 Rango de Datos")
    # Por defecto últimos 90 días para que sea rápido
    d_end = datetime.now().date()
    d_start = d_end - timedelta(days=90)
    
    date_range = st.sidebar.date_input("Filtrar historia:", [d_start, d_end])
    
    # Manejo robusto del selector de fecha
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = d_start, d_end # Fallback

    # Carga de datos filtrada
    providers, df = fetch_fleet_data(user['fleet'], user['role'], user['bus'], start_date, end_date)
    phone_map = {p['name']: p.get('phone', '') for p in providers}

    # ALERTAS GLOBALES (Sobre los datos cargados)
    urgent, warning = 0, 0
    if not df.empty:
        # Calcular alertas
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        pending_maintenance = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        
        for _, row in pending_maintenance.iterrows():
            current_km = last_km.get(row['bus'], 0)
            diff = row['km_next'] - current_km
            if diff < 0: urgent += 1
            elif diff <= 500: warning += 1

    if urgent > 0: st.sidebar.error(f"🚨 {urgent} VENCIDOS")
    elif warning > 0: st.sidebar.warning(f"⚠️ {warning} PRÓXIMOS")

    # MENÚ
    menu_options = {
        "⛽ Combustible": render_fuel,
        "🏠 Radar": lambda: render_radar(df, user),
        "📊 Reportes": lambda: render_reports(df),
        "🛠️ Taller": lambda: render_workshop(user, providers),
        "💰 Contabilidad": lambda: render_accounting(df, user, phone_map),
        "🏢 Directorio": lambda: render_directory(providers, user)
    }
    
    if user['role'] == 'owner':
        menu_options["👥 Personal"] = lambda: render_personnel(user)

    choice = st.sidebar.radio("Navegación", list(menu_options.keys()))
    
    st.divider()
    # Ejecutar función
    menu_options[choice]()

    # Logout
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 CERRAR SESIÓN"):
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

# --- 5. FUNCIONES DE VISTAS ---

def render_personnel(user):
    st.header("Gestión de Personal")
    with st.expander("➕ Agregar Conductor", expanded=False):
        with st.form("new_driver"):
            c1, c2, c3 = st.columns(3)
            nm = c1.text_input("Nombre").upper().strip()
            ce = c2.text_input("Cédula")
            te = c3.text_input("Teléfono")
            if st.form_submit_button("Guardar") and REFS and nm:
                REFS["fleets"].document(user['fleet']).collection("authorized_users").document(nm).set(
                    {"active": True, "cedula": ce, "phone": te, "date": datetime.now().isoformat()}
                )
                st.success("Guardado"); st.rerun()

    if REFS:
        st.write("### Nómina Activa")
        users_ref = REFS["fleets"].document(user['fleet']).collection("authorized_users")
        # Mostrar en grid
        cols = st.columns(3)
        i = 0
        for us in users_ref.stream():
            d = us.to_dict()
            if d.get('role') != 'admin':
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{us.id}**")
                        st.caption(f"🆔 {d.get('cedula','-')} | 📞 {d.get('phone','-')}")
                        c1, c2 = st.columns(2)
                        
                        btn_label = "Bloquear" if d.get('active') else "Activar"
                        btn_color = "primary" if d.get('active') else "secondary"
                        
                        if c1.button(btn_label, key=f"s{us.id}"):
                            users_ref.document(us.id).update({"active": not d.get('active')})
                            st.rerun()
                        if c2.button("Borrar", key=f"d{us.id}"):
                            users_ref.document(us.id).delete()
                            st.rerun()
                i += 1

def render_reports(df):
    st.header("Reportes de Flota")
    
    if df.empty:
        st.warning("No hay datos en el rango de fechas seleccionado.")
        return

    t1, t2 = st.tabs(["🚦 Estado Actual", "📜 Historial Económico"])
    
    with t1:
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        maint_view = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        
        report_data = []
        for _, r in maint_view.iterrows():
            ckm = last_km.get(r['bus'], 0)
            diff = r['km_next'] - ckm
            status = "🔴 VENCIDO" if diff < 0 else "🟡 PRÓXIMO" if diff <= 500 else "🟢 OK"
            report_data.append({
                "Estado": status, "Bus": r['bus'], "Item": r['category'], 
                "KM Actual": ckm, "Meta": r['km_next'], "Restante": diff,
                "Último Reg": r['date'].strftime('%d/%m/%Y')
            })
            
        rdf = pd.DataFrame(report_data)
        if not rdf.empty:
            def color_status(val):
                color = '#ffcccc' if 'VENCIDO' in val else '#fff3cd' if 'PRÓXIMO' in val else '#d4edda'
                return f'background-color: {color}; color: black; font-weight: bold'
            
            st.dataframe(rdf.style.applymap(color_status, subset=['Estado']), use_container_width=True)
        else:
            st.info("No hay mantenimientos preventivos registrados.")

    with t2:
        c1, c2 = st.columns(2)
        sel_bus = c1.selectbox("Filtrar Unidad", ["Todas"] + sorted(df['bus'].unique().tolist()))
        sel_cat = c2.selectbox("Filtrar Categoría", ["Todas"] + sorted(df['category'].unique().tolist()))
        
        df_fil = df.copy()
        if sel_bus != "Todas": df_fil = df_fil[df_fil['bus'] == sel_bus]
        if sel_cat != "Todas": df_fil = df_fil[df_fil['category'] == sel_cat]
        
        # Métricas Económicas
        m1, m2, m3 = st.columns(3)
        total_mec = df_fil['mec_cost'].sum()
        total_rep = df_fil['com_cost'].sum()
        
        m1.metric("Mano de Obra", f"${total_mec:,.2f}")
        m2.metric("Repuestos/Comb.", f"${total_rep:,.2f}")
        m3.metric("GASTO TOTAL", f"${total_mec + total_rep:,.2f}", delta_color="inverse")
        
        st.dataframe(df_fil[['date', 'bus', 'category', 'observations', 'km_current', 'mec_cost', 'com_cost']].sort_values('date', ascending=False), use_container_width=True, hide_index=True)

def render_accounting(df, user, phone_map):
    st.header("Cuentas por Pagar")
    if df.empty: 
        st.info("Sin registros en el período seleccionado.")
        return

    # Gráfico resumen
    if user['role'] == 'owner':
        df['total_cost'] = df['mec_cost'] + df['com_cost']
        chart_data = df.groupby('bus')['total_cost'].sum()
        st.bar_chart(chart_data)

    pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
    if pend.empty: 
        st.success("🎉 No hay deudas pendientes en este período.")
        return

    st.write(f"Deudas encontradas: {len(pend)}")
    
    for _, r in pend.iterrows():
        with st.container(border=True):
            col_info, col_pay = st.columns([1, 2])
            
            with col_info:
                st.subheader(f"Bus {r['bus']}")
                st.write(f"**{r['category']}**")
                st.caption(f"{r['date'].strftime('%d-%m-%Y')}")

            with col_pay:
                c1, c2 = st.columns(2)
                # Lógica de pago refactorizada
                def payment_widget(col, type_prefix, cost_col, paid_col, name_col, label):
                    debt = r[cost_col] - r[paid_col]
                    if debt > 0:
                        col.metric(f"Deuda {label}", f"${debt:,.2f}", delta=-debt)
                        if user['role'] == 'owner':
                            val = col.number_input(f"Abonar {label}", key=f"{type_prefix}{r['id']}", max_value=float(debt))
                            if col.button(f"Pagar {label}", key=f"btn_{type_prefix}{r['id']}") and REFS:
                                REFS["data"].collection("logs").document(r['id']).update({paid_col: firestore.Increment(val)})
                                
                                # WhatsApp Link
                                phone = phone_map.get(r.get(name_col), '')
                                msg = f"Abono: ${val} - {label} ({r['category']} - Bus {r['bus']})"
                                clean_phone = phone.replace('+', '').strip()
                                if clean_phone:
                                    link = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"
                                    col.markdown(f"[📲 Enviar WhatsApp]({link})")
                                st.rerun()

                payment_widget(c1, "m", "mec_cost", "mec_paid", "mec_name", "Mecánico")
                payment_widget(c2, "c", "com_cost", "com_paid", "com_name", "Repuestos")

def render_workshop(user, providers):
    st.header("Registro de Mantenimiento")
    mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    with st.form("workshop_form"):
        col_type, col_cat = st.columns([1, 2])
        m_type = col_type.radio("Tipo", ["Preventivo (Genera Alerta)", "Correctivo"])
        category = col_cat.selectbox("Sistema", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Carrocería", "Vidrios", "Otro"])
        
        obs = st.text_area("Detalle del trabajo realizado")
        
        c1, c2 = st.columns(2)
        km_curr = c1.number_input("KM Actual", min_value=0)
        km_next = c2.number_input("Próximo Cambio (Meta)", min_value=km_curr) if "Preventivo" in m_type else 0
        
        st.markdown("---")
        st.caption("Costos")
        
        c3, c4 = st.columns(2)
        # Mecánico
        mec_name = c3.selectbox("Mecánico", ["N/A"] + mecs)
        mec_cost = c3.number_input("Costo Mano Obra ($)", min_value=0.0)
        mec_paid = c3.number_input("Abonado M.O.", min_value=0.0)
        
        # Repuestos
        com_name = c4.selectbox("Comercio Repuestos", ["N/A"] + coms)
        com_cost = c4.number_input("Costo Repuestos ($)", min_value=0.0)
        com_paid = c4.number_input("Abonado Repuestos", min_value=0.0)
        
        if st.form_submit_button("💾 GUARDAR REGISTRO", type="primary"):
            if mec_paid > mec_cost or com_paid > com_cost:
                st.error("Error: El abono no puede ser mayor al costo.")
            elif REFS:
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'], 
                    "bus": user['bus'], 
                    "date": datetime.now().isoformat(),
                    "category": category, 
                    "observations": obs, 
                    "km_current": km_curr, 
                    "km_next": km_next,
                    "mec_name": mec_name, "mec_cost": mec_cost, "mec_paid": mec_paid, 
                    "com_name": com_name, "com_cost": com_cost, "com_paid": com_paid
                })
                st.toast("✅ Mantenimiento registrado correctamente")
                time.sleep(1)
                st.rerun()

def render_directory(providers, user):
    st.header("Directorio de Proveedores")
    with st.expander("➕ Nuevo Proveedor"):
        with st.form("new_prov"):
            n = st.text_input("Nombre Comercial").upper()
            p = st.text_input("WhatsApp (ej: 59399...)")
            t = st.selectbox("Categoría", ["Mecánico", "Comercio"])
            if st.form_submit_button("Guardar") and REFS and n:
                REFS["data"].collection("providers").add({"name":n, "phone":p, "type":t, "fleetId":user['fleet']})
                st.rerun()
    
    if providers:
        st.write(f"Total: {len(providers)}")
        for p in providers:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{p['name']}**")
                c1.caption(f"{p['type']} • {p.get('phone', 'Sin número')}")
                
                ph = p.get('phone', '').replace('+', '').strip()
                if ph:
                    c2.link_button("WhatsApp", f"https://wa.me/{ph}")

def render_radar(df, user):
    st.subheader("Radar de Flota")
    buses = sorted(df['bus'].unique()) if user['role']=='owner' else [user['bus']]
    
    if not buses: 
        st.info("No hay datos en el rango seleccionado. Intenta ampliar la fecha en el menú lateral.")
        return

    cols = st.columns(3)
    for i, bus in enumerate(buses):
        with cols[i % 3]:
            bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
            if bus_df.empty: continue
            
            latest = bus_df.iloc[0]
            days_inactive = (datetime.now() - latest['date']).days
            
            status_color = "#28a745" # Green
            status_text = "OPERATIVO"
            
            pending = bus_df[bus_df['km_next'] > 0]
            if not pending.empty:
                diff = pending.iloc[0]['km_next'] - latest['km_current']
                if diff < 0: 
                    status_color = "#dc3545"; status_text = "MANT. VENCIDO" # Red
                elif diff <= 500:
                    status_color = "#ffc107"; status_text = "MANT. PRÓXIMO" # Warning
            
            if days_inactive > 5:
                status_text = f"INACTIVO ({days_inactive}d)"
                status_color = "#6c757d" # Gray

            st.markdown(f"""
            <div style="border:1px solid #ddd; padding:15px; border-radius:12px; border-top: 6px solid {status_color}; margin-bottom:15px; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin:0; color: #333;">Bus {bus}</h3>
                <p style="font-size:28px; font-weight:800; margin:5px 0; color: #1E1E1E;">{latest['km_current']:,.0f} km</p>
                <div style="background-color:{status_color}; color: white; padding: 2px 8px; border-radius: 4px; display: inline-block; font-size: 12px; font-weight: bold;">
                    {status_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

def render_fuel():
    user = st.session_state.user
    st.header("Carga de Combustible")
    with st.form("fuel_form"):
        c1, c2, c3 = st.columns(3)
        km = c1.number_input("Kilometraje", min_value=0)
        gal = c2.number_input("Galones", min_value=0.0, step=0.1)
        cost = c3.number_input("Costo Total ($)", min_value=0.0, step=0.01)
        
        if st.form_submit_button("REGISTRAR", type="primary") and REFS:
            REFS["data"].collection("logs").add({
                "fleetId": user['fleet'],
                "bus": user['bus'],
                "date": datetime.now().isoformat(),
                "category": "Combustible",
                "km_current": km,
                "gallons": gal,
                "com_cost": cost,
                "com_paid": cost 
            })
            st.success("Carga registrada")
            time.sleep(0.5)
            st.rerun()

# --- 6. PUNTO DE ENTRADA ---

if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {
            'role': params.get("r"), 'fleet': params.get("f"), 
            'name': params.get("u"), 'bus': params.get("b", "0")
        }
        st.rerun()
    else:
        ui_render_login()
else:
    main_app()
