import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import FailedPrecondition
import google.generativeai as genai
import plotly.express as px
import time
import urllib.parse
import base64

def render_workshop(user, providers):
    st.header("🛠️ Registro de Taller")
    
    # --- HORA AUTOMÁTICA DEL SISTEMA ---
    # Captura la hora exacta del momento y lugar donde se registra
    fecha_registro = datetime.now().isoformat()
    
    mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    # --- 📸 CÁMARA FUERA DEL FORMULARIO (OPCIONAL) ---
    st.write("📸 **Foto del trabajo o factura (Opcional)**")
    # Al estar fuera del form, se procesa en tiempo real y no bloquea el guardado
    foto_archivo = st.camera_input("Capturar evidencia", key="workshop_camera_v5")
    
    if not foto_archivo:
        st.info("💡 Nota: Puedes subir la foto o continuar solo con los datos si el celular tiene problemas.")

    # --- 📝 FORMULARIO DE DATOS ---
    with st.form("workshop_form_data"):
        tp = st.radio("Tipo", ["Preventivo", "Correctivo"], horizontal=True)
        
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Otro"])
        obs = st.text_area("Detalle")
        
        ka = c1.number_input("KM Actual", min_value=0)
        kn = c2.number_input("Próximo", min_value=ka) if tp == "Preventivo" else 0
        
        st.divider()
        col_m, col_r = st.columns(2)
        
        # Mecánico
        mn = col_m.selectbox("Mecánico", ["N/A"] + mecs)
        mc = col_m.number_input("Mano Obra $", min_value=0.0)
        mp = col_m.number_input("Abono MO $", min_value=0.0) 
        
        # Repuestos
        rn = col_r.selectbox("Comercio", ["N/A"] + coms)
        rc = col_r.number_input("Repuestos $", min_value=0.0)
        rp = col_r.number_input("Abono Rep $", min_value=0.0)
        
        # Botón de envío
        enviar = st.form_submit_button("💾 GUARDAR REGISTRO", type="primary", use_container_width=True)
        
        if enviar:
            # VALIDACIÓN: Solo el kilometraje sigue siendo estrictamente obligatorio
            if ka <= 0:
                st.error("❌ ERROR: El kilometraje debe ser mayor a 0.")
            else:
                # --- PROCESAR FOTO SOLO SI EXISTE ---
                base64_photo = ""
                if foto_archivo:
                    import base64
                    bytes_data = foto_archivo.getvalue()
                    base64_photo = base64.b64encode(bytes_data).decode()
                
                # --- GUARDAR EN FIREBASE ---
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": user['bus'],
                    "date": fecha_registro, # <--- Hora automática
                    "category": cat,
                    "observations": obs,
                    "km_current": ka,
                    "km_next": kn,
                    "mec_name": mn,
                    "mec_cost": mc,
                    "mec_paid": mp,
                    "com_name": rn,
                    "com_cost": rc,
                    "com_paid": rp,
                    "photo_b64": base64_photo # Si no hay foto, se guarda vacío
                })
                
                st.cache_data.clear()
                st.success("✅ ¡Registro guardado con éxito!")
                time.sleep(1)
                st.rerun()

# --- 1. CONFIGURACIÓN Y ESTILOS ---
APP_CONFIG = {
    "APP_ID": "itero-titanium-v15",
    "MASTER_KEY": "ADMIN123",
    "VERSION": "10.5.0 Itero Master AI", # Versión con IA Corregida
    "LOGO_URL": "Gemini_Generated_Image_buyjdmbuyjdmbuyj.png", # Tu logo
    "BOSS_PHONE": "0999999999" # <--- CAMBIA ESTO POR TU NÚMERO REAL
}

UI_COLORS = {
    "primary": "#1E1E1E",
    "danger": "#FF4B4B",
    "success": "#28a745",
    "warning": "#ffc107",
    "bg_metric": "#f8f9fa"
}

# Corregido de Itaro a Itero
st.set_page_config(page_title="Itero", layout="wide", page_icon="🚛")

# Estilos CSS Profesionales (Tu código original)
st.markdown(f"""
    <style>
    /* Título Principal */
    .main-title {{ font-size: 65px; font-weight: 900; background: linear-gradient(45deg, #1E1E1E, #4A4A4A); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 20px; }}
    
    /* Botones Modernos de Streamlit (Generales) */
    .stButton>button {{
        width: 100%;
        border-radius: 12px;
        border: none;
        padding: 12px 20px;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        color: #1E1E1E;
        font-weight: 700;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }}
    .stButton>button:hover {{
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e0 100%);
        border: none;
    }}

    /* Botón Primario (Ingresar / Guardar) */
    div.stButton > button:first-child[kind="primary"] {{
        background: linear-gradient(135deg, #1e1e1e 0%, #434343 100%);
        color: white;
    }}

    /* Botón de WhatsApp Custom */
    .btn-whatsapp {{
        display: inline-block;
        background: linear-gradient(135deg, #25D366 0%, #128C7E 100%);
        color: white !important;
        text-decoration: none;
        padding: 15px 25px;
        border-radius: 12px;
        font-weight: 800;
        text-align: center;
        width: 100%;
        box-shadow: 0 4px 15px rgba(37, 211, 102, 0.3);
        transition: all 0.3s ease;
        border: none;
    }}
    .btn-whatsapp:hover {{
        transform: scale(1.02);
        box-shadow: 0 6px 20px rgba(37, 211, 102, 0.4);
    }}

    /* Tarjetas de Datos */
    .metric-box {{
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05);
        border: 1px solid #f0f0f0;
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

# --- 2. CONFIGURACIÓN DE IA (SOLUCIÓN AL ERROR 404) ---
try:
    if "GEMINI_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_KEY"]["api_key"])
        HAS_AI = True
    else:
        HAS_AI = False
except Exception as e:
    HAS_AI = False

def get_ai_analysis(df_bus, bus_id, fleet_id):
    """IA Holística: Corregida para evitar errores de modelo no encontrado."""
    if not HAS_AI: return "⚠️ IA no disponible."
    
    try:
        # Recuperar reglas de entrenamiento
        fleet_doc = REFS["fleets"].document(fleet_id).get()
        ai_rules = fleet_doc.to_dict().get("ai_rules", "") if fleet_doc.exists else ""

        cols = ['date', 'category', 'observations', 'km_current', 'gallons', 'mec_cost', 'com_cost']
        available_cols = [c for c in cols if c in df_bus.columns]
        summary = df_bus[available_cols].head(15).to_string()
        
        prompt = f"""
        Actúa como el Jefe de Taller Experto de ITERO. Analiza el historial del Bus {bus_id}:
        {summary}
        
        REGLAS DE TU DUEÑO:
        {ai_rules if ai_rules else "Analiza combustible y mantenimiento buscando anomalías."}

        Dame 3 puntos breves (Diagnóstico, Alerta de Costos/Fraudes, Recomendación). Usa emojis.
        """
        
        # --- SOLUCIÓN AL 404: Listar modelos disponibles dinámicamente ---
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priorizar flash, luego pro, luego el primero disponible
        model_to_use = "models/gemini-1.5-flash" # Default
        if valid_models:
            model_to_use = valid_models[0]
            for m in valid_models:
                if "1.5-flash" in m:
                    model_to_use = m
                    break

        model = genai.GenerativeModel(model_to_use)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error de conexión IA: {str(e)}"

# --- 3. CAPA DE DATOS (FIREBASE INTEGRADO) ---
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

@st.cache_data(ttl=300)
def fetch_fleet_data(fleet_id: str, role: str, bus_id: str, start_d: date, end_d: date):
    if not REFS: return [], pd.DataFrame()
    try:
        p_docs = REFS["data"].collection("providers").where("fleetId", "==", fleet_id).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        
        dt_start, dt_end = datetime.combine(start_d, datetime.min.time()), datetime.combine(end_d, datetime.max.time())
        base_query = REFS["data"].collection("logs").where("fleetId", "==", fleet_id)
        if role == 'driver': base_query = base_query.where("bus", "==", bus_id)
            
        query = base_query.where("date", ">=", dt_start.isoformat()).where("date", "<=", dt_end.isoformat())
        logs = [l.to_dict() | {"id": l.id} for l in query.stream()]

        cols_config = {'bus': '0', 'category': '', 'observations': '', 'km_current': 0, 'km_next': 0, 'mec_cost': 0, 'com_cost': 0, 'mec_paid': 0, 'com_paid': 0, 'gallons': 0}
        
        if not logs: return provs, pd.DataFrame(columns=list(cols_config.keys()) + ['date'])
        
        df = pd.DataFrame(logs)
        for col, val in cols_config.items():
            if col not in df.columns: df[col] = val
            if isinstance(val, (int, float)): df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df
    except Exception as e:
        st.error(f"Error: {e}"); return [], pd.DataFrame()

# --- 4. UI LOGIN Y SUPER ADMIN (Tu código completo) ---
def ui_render_login():
    st.markdown('<div class="main-title">Itero AI</div>', unsafe_allow_html=True)
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
    if not REFS: st.error("Offline"); return
    doc = REFS["fleets"].document(f_in).get()
    
    if not doc.exists: 
        st.error("❌ Código de flota no registrado.")
        return
        
    data = doc.to_dict()
    
    # --- BLOQUE DE SUSPENSIÓN CORDIAL ---
    if data.get('status') == 'suspended':
        # Buscamos el contacto que guardaste en el Super Admin
        sup_snap = REFS["data"].get()
        # Si no has guardado nada aún, usa tus datos por defecto
        contacto_maestro = "jlmaldonado173@gmail.com o 0964014007"
        contacto = sup_snap.to_dict().get("support_contact", contacto_maestro) if sup_snap.exists else contacto_maestro
        
        st.warning(f"""
            ### ℹ️ Aviso de Cuenta
            Estimado usuario, su acceso a **Itero AI** se encuentra temporalmente inactivo. 
            Queremos que siga gestionando su flota con la mejor tecnología, por lo cual, para reactivar sus servicios, le invitamos cordialmente a ponerse en contacto con nuestra administración:
            
            📧 **{contacto}**
            
            Estaremos encantados de ayudarle a continuar con su operación.
        """)
        return
    # ------------------------------------

    access = False; role = ""; assigned_bus = "0"
    if "Adm" in r_in:
        if data.get('password') == pass_in: 
            access = True; role = 'owner'
        else: 
            st.error("🔒 Contraseña incorrecta.")
    else:
        # Login ciego para conductor
        auth = REFS["fleets"].document(f_in).collection("authorized_users").document(u_in).get()
        if auth.exists and auth.to_dict().get('active', True): 
            access = True; role = 'driver'
            assigned_bus = auth.to_dict().get('bus', '0')
        else: 
            st.error("❌ Usuario no autorizado.")

    if access:
        st.session_state.user = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': assigned_bus}
        st.rerun()

    # ... resto del código de login ...

def handle_register(nid, own, pas):
    if REFS and nid and own and pas:
        ref = REFS["fleets"].document(nid)
        if not ref.get().exists:
            ref.set({"owner": own, "status": "active", "password": pas, "created": datetime.now()})
            ref.collection("authorized_users").document(own).set({"active": True, "role": "admin"})
            st.success("✅ Empresa creada."); st.rerun()
        else: st.error("Código en uso.")

def render_super_admin():
    if not REFS: return
    st.header("⚙️ Panel de Control Maestro (Super Admin)")
    
    # 1. Configuración de contacto (CORRECCIÓN DEL ERROR NOTFOUND)
    with st.expander("🛠️ Configuración de Mensaje de Bloqueo", expanded=True):
        # Datos predeterminados solicitados
        msg_default = "jlmaldonado173@gmail.com o llame al 0964014007"
        
        # Intentamos traer el valor actual si existe
        doc_snap = REFS["data"].get()
        current_msg = doc_snap.to_dict().get("support_contact", msg_default) if doc_snap.exists else msg_default
        
        c_msg = st.text_input("Contacto de soporte para flotas suspendidas", value=current_msg)
        
        if st.button("Guardar Contacto Maestro"):
            # USAMOS .set con merge=True para que si no existe el documento, lo cree sin error
            REFS["data"].set({"support_contact": c_msg}, merge=True)
            st.success("✅ ¡Contacto guardado! Este mensaje aparecerá a las flotas bloqueadas.")

    st.subheader("🏢 Gestión de Empresas Registradas")
    
    # 2. Listado de flotas
    for f in REFS["fleets"].stream():
        d = f.to_dict()
        
        # Conteo de unidades real de esta flota
        unidades = REFS["data"].collection("logs").where("fleetId", "==", f.id).stream()
        bus_list = set([u.to_dict().get('bus') for u in unidades if u.to_dict().get('bus')])
        total_buses = len(bus_list)

        with st.expander(f"Empresa: {f.id} | Dueño: {d.get('owner')} | 🚛 {total_buses} Unidades", expanded=False):
            c1, c2, c3 = st.columns(3)
            
            # Control de Estado (Suspender/Activar)
            is_active = d.get('status') == 'active'
            label = "🔴 SUSPENDER" if is_active else "🟢 ACTIVAR"
            if c1.button(label, key=f"s_{f.id}"):
                REFS["fleets"].document(f.id).update({"status": "suspended" if is_active else "active"})
                st.rerun()
            
            # Cambio de Clave
            new_pass = c2.text_input("Nueva Clave", key=f"p_{f.id}", type="password")
            if c2.button("Cambiar Password", key=f"bp_{f.id}"):
                if new_pass:
                    REFS["fleets"].document(f.id).update({"password": new_pass})
                    st.success("🔑 Clave actualizada")
                else: 
                    st.error("Escribe una clave")

            # Peligro: Eliminar
            if c3.button("🗑️ ELIMINAR FLOTA", key=f"del_{f.id}"):
                REFS["fleets"].document(f.id).delete()
                st.rerun()
# --- 5. VISTAS PRINCIPALES ---
def render_radar(df, user):
    st.subheader("📡 Radar de Flota")
    if df.empty or 'bus' not in df.columns: 
        st.info("⏳ Sin datos actuales."); return

    buses = sorted(df['bus'].unique()) if user['role']=='owner' else [user['bus']]
    
    if user['role'] == 'driver':
        bus = user['bus']
        bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
        if bus_df.empty: st.warning("Sin historial."); return
        latest = bus_df.iloc[0]; pending = bus_df[bus_df['km_next'] > 0]
        
        # Lógica de colores y estados
        color = "#28a745"; msg = "✅ UNIDAD OPERATIVA"; wa = ""
        if not pending.empty:
            diff = pending.iloc[0]['km_next'] - latest['km_current']
            if diff < 0: 
                color = "linear-gradient(135deg, #FF4B4B 0%, #8B0000 100%)" # Rojo moderno
                msg = f"🚨 VENCIDO: {pending.iloc[0]['category']}"
                wa = f"Jefe, mi unidad {bus} tiene vencido {pending.iloc[0]['category']}."
            elif diff <= 500: 
                color = "linear-gradient(135deg, #ffc107 0%, #e67e22 100%)" # Naranja moderno
                msg = f"⚠️ PRÓXIMO: {pending.iloc[0]['category']}"
                wa = f"Jefe, al Bus {bus} le toca {pending.iloc[0]['category']} pronto."
            else:
                color = "linear-gradient(135deg, #28a745 0%, #1e7e34 100%)" # Verde moderno

        # Tarjeta de Conductor Moderna
        st.markdown(f"""
            <div class="driver-card" style="background:{color}; border:none; padding:30px;">
                <h1 style="margin:0; font-size:45px; letter-spacing:-1px;">BUS {bus}</h1>
                <h3 style="opacity:0.9; font-weight:400;">{msg}</h3>
                <div style="background:rgba(255,255,255,0.2); display:inline-block; padding:10px 30px; border-radius:50px; margin-top:15px;">
                    <span style="font-size:40px; font-weight:900;">{latest['km_current']:,.0f} KM</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        if wa:
            link = f"https://wa.me/{format_phone(APP_CONFIG['BOSS_PHONE'])}?text={urllib.parse.quote(wa)}"
            st.markdown(f'<a href="{link}" target="_blank" class="btn-whatsapp">📲 NOTIFICAR AL JEFE</a>', unsafe_allow_html=True)
            st.write("") # Espaciador
        
        st.write("### 📜 Mi Historial")
        st.dataframe(bus_df[['date', 'category', 'observations', 'km_current']].head(10).assign(date=lambda x: x['date'].dt.strftime('%Y-%m-%d')), use_container_width=True, hide_index=True)
        return

    # VISTA DUEÑO
    for bus in buses:
        bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
        if bus_df.empty: continue
        latest = bus_df.iloc[0]
        
        color_icon = "🟢"
        if not bus_df[bus_df['km_next'] > 0].empty:
            diff = bus_df[bus_df['km_next'] > 0].iloc[0]['km_next'] - latest['km_current']
            if diff < 0: color_icon = "🔴"
            elif diff <= 500: color_icon = "🟡"

        with st.expander(f"{color_icon} BUS {bus} | KM: {latest['km_current']:,.0f}"):
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                st.dataframe(bus_df[['date', 'category', 'km_current', 'mec_cost']].head(3).assign(date=lambda x: x['date'].dt.strftime('%Y-%m-%d')), use_container_width=True, hide_index=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            with c2:
                # Botón de IA con estilo moderno (usando el tipo primario de Streamlit que ya estilizamos)
                if st.button(f"🤖 Diagnóstico IA", key=f"ai_{bus}", type="primary", use_container_width=True):
                    with st.spinner("IA Analizando..."):
                        st.info(get_ai_analysis(bus_df, bus, user['fleet']))

def render_ai_training(user):
    st.header("🧠 Entrenar IA Itero")
    st.write("Configura tus reglas (Ej: Aceite cada 10k km, alerta si el gasto supera $500).")
    doc_ref = REFS["fleets"].document(user['fleet'])
    rules = doc_ref.get().to_dict().get("ai_rules", "") if doc_ref.get().exists else ""
    new_rules = st.text_area("Instrucciones de la Flota:", value=rules, height=200)
    if st.button("💾 Guardar y Entrenar IA"):
        doc_ref.set({"ai_rules": new_rules}, merge=True); st.success("IA Actualizada"); st.rerun()

def render_reports(df):
    st.header("📊 Reportes y Auditoría")
    if df.empty: 
        st.warning("No hay datos.")
        return
        
    t1, t2, t3 = st.tabs(["📊 Gráficos Visuales", "🚦 Estado de Unidades", "📜 Historial Detallado"])
    
    with t1:
        c1, c2 = st.columns(2)
        df['total_cost'] = df.get('mec_cost', 0) + df.get('com_cost', 0)
        c1.plotly_chart(px.pie(df, values='total_cost', names='category', title='Gastos por Categoría'), use_container_width=True)
        c2.plotly_chart(px.bar(df, x='bus', y='total_cost', title='Gastos por Unidad'), use_container_width=True)

    with t2:
        last_km = df.sort_values('date').groupby('bus')['km_current'].last()
        view = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        data = [{"bus": r['bus'], "Estado": "🔴 VENCIDO" if (r['km_next'] - last_km.get(r['bus'],0)) < 0 else "🟢 OK", "Item": r['category']} for _, r in view.iterrows()]
        if data:
            st.dataframe(pd.DataFrame(data).sort_values('bus'), use_container_width=True, hide_index=True)

    with t3:
        st.subheader("📜 Bitácora de Movimientos")
        # Ordenamos por fecha descendente
        df_sorted = df.sort_values('date', ascending=False)
        
        for _, r in df_sorted.iterrows():
            # Título del expander con fecha y bus
            fecha_str = r['date'].strftime('%d/%m/%Y')
            with st.expander(f"📅 {fecha_str} | Bus {r['bus']} | {r['category']}"):
                col_txt, col_img = st.columns([2, 1])
                
                with col_txt:
                    st.write(f"**Detalle:** {r.get('observations', 'Sin detalle')}")
                    st.write(f"**KM:** {r['km_current']:,.0f}")
                    if r.get('mec_name') and r['mec_name'] != "N/A":
                        st.caption(f"👨‍🔧 Mecánico: {r['mec_name']} (${r['mec_cost']})")
                    if r.get('com_name') and r['com_name'] != "N/A":
                        st.caption(f"🛒 Comercio: {r['com_name']} (${r['com_cost']})")
                
                with col_img:
                    # --- AQUÍ SE MUESTRA LA FOTO CAPTURADA ---
                    if "photo_b64" in r and r["photo_b64"]:
                        try:
                            st.image(f"data:image/jpeg;base64,{r['photo_b64']}", 
                                     caption="Evidencia capturada", 
                                     use_container_width=True)
                        except:
                            st.error("Error al cargar imagen")
                    else:
                        st.info("🚫 Sin foto")

def render_accounting(df, user, phone_map):
    st.header("💰 Contabilidad y Abonos")
    
    # Filtrar registros con deudas pendientes
    pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
    
    if pend.empty:
        st.success("🎉 Todo al día. No hay deudas pendientes.")
        return
    
    for bus in sorted(pend['bus'].unique()):
        # Expander moderno para cada Bus
        with st.expander(f"🚌 DEUDAS BUS {bus}", expanded=True):
            bus_pend = pend[pend['bus'] == bus].sort_values('date', ascending=False)
            
            for _, r in bus_pend.iterrows():
                # Contenedor de tarjeta para cada trabajo
                st.markdown(f"""
                <div class="metric-box" style="margin-bottom:15px;">
                    <p style="margin:0; color:#666; font-size:12px;">{r['date'].strftime('%d-%m-%Y')}</p>
                    <h4 style="margin:0 0 10px 0;">{r['category']}</h4>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                
                # Configuración de los dos tipos de deudas posibles por registro
                deudas = [
                    ('m', 'mec_cost', 'mec_paid', 'mec_name', '👨‍🔧 Mano de Obra'),
                    ('c', 'com_cost', 'com_paid', 'com_name', '🛒 Repuestos/Comercio')
                ]
                
                for t, cost, paid, name, lbl in deudas:
                    debt = r[cost] - r[paid]
                    col = c1 if t == 'm' else c2
                    
                    if debt > 0:
                        with col:
                            # Visualización de la deuda
                            st.metric(lbl, f"${debt:,.2f}", help=f"Proveedor: {r.get(name,'No asignado')}")
                            
                            if user['role'] == 'owner':
                                # Input de abono con estilo
                                v = st.number_input(
                                    f"Abonar a {r.get(name,'')}", 
                                    key=f"in_{t}{r['id']}", 
                                    max_value=float(debt), 
                                    min_value=0.0,
                                    step=10.0
                                )
                                
                                if st.button(f"Registrar Pago", key=f"btn_{t}{r['id']}", type="primary", use_container_width=True):
                                    # 1. Actualización en Firebase
                                    REFS["data"].collection("logs").document(r['id']).update({
                                        paid: firestore.Increment(v)
                                    })
                                    
                                    # 2. Preparación del mensaje de WhatsApp
                                    nuevo_saldo = debt - v
                                    ph = format_phone(phone_map.get(r.get(name), ''))
                                    
                                    if ph:
                                        texto = (
                                            f"*PROBANTE DE PAGO - ITERO AI*\n"
                                            f"--------------------------------\n"
                                            f"Hola *{r.get(name,'')}*, se ha registrado un abono:\n\n"
                                            f"✅ *Abono:* ${v:,.2f}\n"
                                            f"🚛 *Unidad:* Bus {bus}\n"
                                            f"🔧 *Detalle:* {r['category']} ({lbl})\n"
                                            f"📉 *Saldo restante:* ${nuevo_saldo:,.2f}\n\n"
                                            f" _Enviado desde Itero Master AI_ "
                                        )
                                        
                                        link = f"https://wa.me/{ph}?text={urllib.parse.quote(texto)}"
                                        
                                        # 3. Mostrar botón moderno de WhatsApp
                                        st.markdown(f"""
                                            <a href="{link}" target="_blank" class="btn-whatsapp" style="text-decoration:none;">
                                                📲 ENVIAR COMPROBANTE WHATSAPP
                                            </a>
                                            <br>
                                        """, unsafe_allow_html=True)
                                    
                                    st.success(f"Abono de ${v} registrado.")
                                    fetch_fleet_data.clear()
                                    time.sleep(2)
                                    st.rerun()
                st.markdown("---")

def render_workshop(user, providers):
    st.header("🛠️ Gestión de Taller")
    
    mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    # --- PASO 1: CÁMARA FUERA DEL FORMULARIO ---
    # Esto asegura que la foto se guarde en la sesión apenas se toma
    st.write("📸 **Captura de Evidencia (Obligatoria)**")
    foto_captura = st.camera_input("Tome la foto de la factura o trabajo", key="camera_workshop_final")

    # --- PASO 2: EL FORMULARIO DE DATOS ---
    with st.form("workshop_data_form", clear_on_submit=True):
        tp = st.radio("Tipo de Mantenimiento", ["Preventivo", "Correctivo"], horizontal=True)
        
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Otro"])
        obs = st.text_area("Detalle del trabajo realizado")
        
        ka = c1.number_input("KM Actual", min_value=0)
        kn = c2.number_input("Próximo Mantenimiento (KM)", min_value=ka) if tp == "Preventivo" else 0
        
        st.divider()
        col_a, col_b = st.columns(2)
        mn = col_a.selectbox("Mecánico", ["N/A"] + mecs)
        mc = col_a.number_input("Costo Mano Obra $", min_value=0.0)
        mp = col_a.number_input("Abono Inicial MO $", min_value=0.0, max_value=mc)
        
        rn = col_b.selectbox("Comercio / Repuestos", ["N/A"] + coms)
        rc = col_b.number_input("Costo Repuestos $", min_value=0.0)
        rp = col_b.number_input("Abono Inicial Rep $", min_value=0.0, max_value=rc)
        
        # Botón de envío
        submit = st.form_submit_button("💾 GUARDAR REGISTRO", type="primary", use_container_width=True)
        
        if submit:
            # Ahora la validación de foto_captura funcionará correctamente
            if not foto_captura:
                st.error("❌ ERROR: Debe tomar la foto arriba antes de presionar Guardar.")
            elif ka <= 0:
                st.error("❌ ERROR: El kilometraje debe ser mayor a 0.")
            else:
                # Procesar imagen a Base64 para guardarla
                import base64
                img_bytes = foto_captura.getvalue()
                foto_b64 = base64.b64encode(img_bytes).decode()
                
                datos = {
                    "fleetId": user['fleet'],
                    "bus": user['bus'],
                    "date": datetime.now().isoformat(),
                    "category": cat,
                    "observations": obs,
                    "km_current": ka,
                    "km_next": kn,
                    "mec_name": mn, "mec_cost": mc, "mec_paid": mp,
                    "com_name": rn, "com_cost": rc, "com_paid": rp,
                    "photo_b64": foto_b64, # Guardamos la imagen real
                    "has_photo": True
                }
                
                REFS["data"].collection("logs").add(datos)
                st.cache_data.clear()
                st.success("✅ ¡Guardado con éxito!")
                time.sleep(1)
                st.rerun()

def render_fuel():
    u = st.session_state.user
    st.header("⛽ Registro de Combustible")
    
    # 1. Ajuste de Hora Local (Ecuador UTC-5)
    # Evita que el registro salga con fecha de mañana
    fecha_ecuador = (datetime.now() - timedelta(hours=5)).isoformat()
    
    with st.form("fuel_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        k = c1.number_input("Kilometraje Actual", min_value=0)
        g = c2.number_input("Galones", min_value=0.0)
        c = c3.number_input("Costo Total $", min_value=0.0)
        
        if st.form_submit_button("🚀 REGISTRAR CARGA", type="primary", use_container_width=True):
            if k > 0 and g > 0 and c > 0:
                # 2. Guardado en Firebase con fecha corregida
                REFS["data"].collection("logs").add({
                    "fleetId": u['fleet'],
                    "bus": u['bus'],
                    "date": fecha_ecuador, # <--- HORA DE ECUADOR
                    "category": "Combustible",
                    "km_current": k,
                    "gallons": g,
                    "com_cost": c,
                    "com_paid": c # Se marca como pagado automáticamente
                })
                
                # 3. Limpieza de caché para actualizar gráficos y tablas
                st.cache_data.clear() 
                st.success("✅ Carga registrada correctamente")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Por favor, llena todos los campos con valores mayores a 0.")

def render_personnel(user):
    st.header("👥 Gestión de Personal")
    
    # 1. Formulario para Nuevo Usuario (Conductor o Mecánico)
    with st.expander("➕ Registrar Nuevo Personal"):
        with st.form("nd"):
            nm = st.text_input("Nombre / Usuario").upper()
            te = st.text_input("Teléfono")
            
            # Selector de ROL: Esto es lo que permite que el sistema sepa quién es mecánico
            rol = st.selectbox("Rol", ["driver", "mechanic"], format_func=lambda x: "🚛 Conductor" if x == "driver" else "🛠️ Mecánico")
            
            bs = st.text_input("Bus Asignado (Poner 0 para Mecánicos)")
            
            if st.form_submit_button("Crear Usuario", type="primary"):
                if nm:
                    REFS["fleets"].document(user['fleet']).collection("authorized_users").document(nm).set({
                        "active": True,
                        "phone": te,
                        "bus": bs,
                        "role": rol # Guardamos el rol elegido
                    })
                    st.cache_data.clear()
                    st.success(f"Usuario {nm} creado como {rol}")
                    st.rerun()
                else:
                    st.error("El nombre es obligatorio")

    st.divider()
    st.subheader("📋 Lista de Personal Autorizado")

    # 2. Lista de usuarios existentes
    usuarios = REFS["fleets"].document(user['fleet']).collection("authorized_users").stream()
    
    for us in usuarios:
        d = us.to_dict()
        # No mostramos al admin en la lista para evitar errores
        if d.get('role') != 'owner' and d.get('role') != 'admin':
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                
                # Identificamos visualmente el rol
                emoji = "🛠️" if d.get('role') == 'mechanic' else "🚛"
                c1.markdown(f"{emoji} **{us.id}**")
                c1.caption(f"Rol: {d.get('role')} | 📱 {d.get('phone')}")
                
                # Edición de unidad asignada
                nb = c2.text_input("Unidad", value=d.get('bus',''), key=f"b_{us.id}")
                
                # Guardar cambios o Borrar
                if nb != d.get('bus',''):
                    if c2.button("💾", key=f"s_{us.id}"): 
                        REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).update({"bus": nb})
                        st.cache_data.clear()
                        st.rerun()
                
                if c3.button("🗑️", key=f"d_{us.id}"): 
                    REFS["fleets"].document(user['fleet']).collection("authorized_users").document(us.id).delete()
                    st.cache_data.clear()
                    st.rerun()
def render_fleet_management(df, user):
    st.header("🚛 Gestión de Flota")
    buses = sorted(df['bus'].unique())
    c1, c2 = st.columns(2)
    
    # --- BLOQUE 1: RENOMBRAR ---
    with c1.container(border=True):
        st.subheader("✏️ Renombrar Unidad")
        old = st.selectbox("Unidad", buses, key="ren_old")
        new = st.text_input("Nuevo Nombre/Número")
        if st.button("Actualizar Nombre") and new:
            for d in REFS["data"].collection("logs").where("fleetId","==",user['fleet']).where("bus","==",old).stream():
                REFS["data"].collection("logs").document(d.id).update({"bus": new})
            st.success("Nombre actualizado"); st.rerun()

# --- BLOQUE 2: BORRAR (CORREGIDO) ---
    with c2.container(border=True):
        st.subheader("🗑️ Borrar Historial")
        dbus = st.selectbox("Eliminar unidad", buses, key="del_bus")
        if st.button("ELIMINAR TODO EL HISTORIAL", type="secondary"):
            # 1. Borrar de la base de datos
            docs = REFS["data"].collection("logs").where("fleetId","==",user['fleet']).where("bus","==",dbus).stream()
            for d in docs:
                REFS["data"].collection("logs").document(d.id).delete()
            
            # 2. LIMPIAR LA CACHE (Esto es lo que te falta)
            st.cache_data.clear() 
            
            # 3. Notificar y refrescar
            st.success(f"✅ Historial de la unidad {dbus} borrado por completo")
            time.sleep(1) # Un pequeño respiro para el sistema
            st.rerun()

    st.divider()

    # --- BLOQUE 3: TRANSFERENCIA DIRECTA (NUEVO) ---
    st.subheader("🚀 Transferencia Directa a otro Dueño Itero")
    st.info("Esta función copia todo el historial de un bus a otra empresa Itero usando su Código de Flota.")
    
    col_t1, col_t2 = st.columns(2)
    target_fleet = col_t1.text_input("Código de Flota Destino").upper().strip()
    bus_to_send = col_t2.selectbox("Bus a transferir", buses, key="send_bus")
    
    if st.button("Realizar Transferencia Directa", type="primary"):
        if not target_fleet:
            st.error("Debes ingresar el código de la flota destino.")
        elif target_fleet == user['fleet']:
            st.error("No puedes transferir datos a tu propia flota.")
        else:
            # 1. Verificar si la flota destino existe en el sistema
            dest_doc = REFS["fleets"].document(target_fleet).get()
            if dest_doc.exists:
                # 2. Consultar registros del bus actual
                logs_to_transfer = REFS["data"].collection("logs")\
                    .where("fleetId", "==", user['fleet'])\
                    .where("bus", "==", bus_to_send).stream()
                
                count = 0
                for doc in logs_to_transfer:
                    data = doc.to_dict()
                    # 3. Cambiamos el dueño al ID de la flota destino
                    data['fleetId'] = target_fleet
                    data['observations'] = f"{data.get('observations', '')} (Importado de {user['fleet']})"
                    
                    # 4. Guardamos en la base de datos como nuevo registro para el destino
                    REFS["data"].collection("logs").add(data)
                    count += 1
                
                if count > 0:
                    st.success(f"✅ ¡Transferencia Exitosa! Se enviaron {count} registros al código {target_fleet}.")
                    st.balloons()
                    # Opcional: WhatsApp al nuevo dueño si tenemos su número
                    dest_data = dest_doc.to_dict()
                    msg_wa = f"Hola, te he transferido el historial de mi Bus {bus_to_send} a tu sistema Itero AI. ¡Ya puedes revisarlo!"
                    st.markdown(f"[📲 Notificar al nuevo dueño por WhatsApp](https://wa.me/?text={urllib.parse.quote(msg_wa)})")
                else:
                    st.warning("No se encontraron registros para este bus.")
            else:
                st.error(f"❌ La flota '{target_fleet}' no existe. Verifica el código con el nuevo dueño.")

def render_directory(providers, user):
    st.header("🏢 Directorio de Proveedores")
    
    # 1. REGISTRO DE NUEVO (Solo Dueño)
    # Agregamos clear_on_submit=True para vaciar las cajas al guardar
    if user['role'] == 'owner':
        with st.expander("➕ Registrar Nuevo Maestro / Proveedor", expanded=False):
            with st.form("new_prov_form", clear_on_submit=True):
                n = st.text_input("Nombre Completo / Taller").upper()
                p = st.text_input("WhatsApp (ej: 0990000000)")
                t = st.selectbox("Especialidad", ["Mecánico", "Comercio", "Llantas", "Frenos", "Electricista", "Otro"])
                
                if st.form_submit_button("Guardar Proveedor", type="primary"):
                    if n and p:
                        REFS["data"].collection("providers").add({
                            "name": n, "phone": p, "type": t, "fleetId": user['fleet']
                        })
                        st.cache_data.clear() 
                        st.success("✅ Guardado con éxito")
                        time.sleep(1)
                        st.rerun()
                    else: 
                        st.error("Faltan datos obligatorios (Nombre y WhatsApp).")

    if not providers:
        st.info("Aún no tienes proveedores registrados.")
        return

    # 2. LISTA DE PROVEEDORES (Visualización para todos los roles)
    for p in providers:
        p_id = p.get('id')
        with st.container(border=True):
            col_info, col_wa = st.columns([2, 1])
            
            col_info.markdown(f"**{p['name']}**")
            col_info.caption(f"🔧 {p['type']} | 📞 {p.get('phone', 'S/N')}")
            
            # Botón de WhatsApp
            if p.get('phone'):
                # Función auxiliar para limpiar el número (debes tenerla definida)
                ph = "".join(filter(str.isdigit, p['phone']))
                if ph.startswith('0'): ph = '593' + ph[1:] # Ajuste para Ecuador
                
                link = f"https://wa.me/{ph}?text=Hola%20{p['name']}"
                col_wa.markdown(
                    f'<a href="{link}" target="_blank" style="text-decoration:none;">'
                    f'<div style="background-color:#25D366; color:white; padding:8px; border-radius:10px; text-align:center; font-weight:bold;">'
                    f'📲 CHAT</div></a>', 
                    unsafe_allow_html=True
                )

            # 3. GESTIÓN DE PROVEEDOR (Solo Dueño)
            if user['role'] == 'owner':
                st.divider()
                c_edit, c_del = st.columns(2)
                
                # Checkbox para abrir edición
                edit_mode = c_edit.checkbox("✏️ Editar", key=f"ed_check_{p_id}")
                
                # Borrado directo
                if c_del.button("🗑️ Eliminar", key=f"del_btn_{p_id}", use_container_width=True):
                    REFS["data"].collection("providers").document(p_id).delete()
                    st.cache_data.clear()
                    st.toast(f"Eliminado: {p['name']}")
                    time.sleep(0.5)
                    st.rerun()

                # Formulario de Edición (Aparece solo si el checkbox está activo)
                if edit_mode:
                    with st.form(f"f_ed_{p_id}"):
                        new_n = st.text_input("Nombre", value=p['name']).upper()
                        new_p = st.text_input("WhatsApp", value=p.get('phone',''))
                        
                        # Lista de tipos para el index
                        tipos = ["Mecánico", "Comercio", "Llantas", "Frenos", "Electricista", "Otro"]
                        idx = tipos.index(p['type']) if p['type'] in tipos else 0
                        
                        new_t = st.selectbox("Tipo", tipos, index=idx)
                        
                        if st.form_submit_button("💾 Guardar Cambios"):
                            REFS["data"].collection("providers").document(p_id).update({
                                "name": new_n, 
                                "phone": new_p, 
                                "type": new_t
                            })
                            st.cache_data.clear()
                            st.success("Actualizado"); time.sleep(0.5); st.rerun()

def render_mechanic_work(user, bus_id, providers):
    st.info(f"Registrando trabajo para la Unidad: **{bus_id}**")
    
    # Buscamos el nombre del comercio en el directorio para que el mecánico elija dónde compró repuestos
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    with st.form("mechanic_log"):
        cat = st.selectbox("Categoría del Daño", ["Mecánica", "Eléctrica", "Frenos", "Suspensión", "Motor"])
        obs = st.text_area("Informe Técnico", placeholder="Describa el daño encontrado y la solución...")
        
        c1, c2 = st.columns(2)
        mo_cost = c1.number_input("Costo Mano de Obra $", min_value=0.0)
        
        st.divider()
        st.write("🛒 **Repuestos Utilizados**")
        store_name = st.selectbox("Comprado en:", ["N/A"] + coms)
        rep_cost = st.number_input("Costo de Repuestos $", min_value=0.0)
        
        # Foto obligatoria del daño o repuesto
        foto = st.camera_input("Capturar evidencia del trabajo")
        
        if st.form_submit_button("ENVIAR REPORTE Y CARGAR A CONTABILIDAD", type="primary"):
            if not foto or not obs:
                st.error("Debe incluir descripción y foto de evidencia.")
            else:
                # Convertir foto
                bytes_data = foto.getvalue()
                b64 = base64.b64encode(bytes_data).decode()
                
                # GUARDAR EN FIREBASE
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": bus_id,
                    "date": datetime.now().isoformat(),
                    "category": cat,
                    "observations": f"REPORTE MECÁNICO ({user['name']}): {obs}",
                    "km_current": 0, # El mecánico no siempre sabe el KM, se puede dejar en 0
                    "mec_name": user['name'], # El nombre del mecánico que inició sesión
                    "mec_cost": mo_cost,
                    "mec_paid": 0, # Se guarda como DEUDA automáticamente
                    "com_name": store_name,
                    "com_cost": rep_cost,
                    "com_paid": 0, # Se guarda como DEUDA
                    "photo_b64": b64
                })
                
                st.cache_data.clear()
                st.success("✅ Reporte enviado. El dueño ya puede ver los costos en Contabilidad.")
                time.sleep(1)
                st.rerun()
def main():
    if 'user' not in st.session_state:
        ui_render_login()
    else:
        u = st.session_state.user
        
        # Logo y Nombre en el Sidebar
        if "LOGO_URL" in APP_CONFIG: 
            st.sidebar.image(APP_CONFIG["LOGO_URL"], width=200)
        st.sidebar.title(f"Itero: {u['name']}")
        
        # Filtro de fechas
        dr = st.sidebar.date_input("Fechas", [date.today() - timedelta(days=90), date.today()])
        
        # Carga de datos base
        provs, df = fetch_fleet_data(u['fleet'], u['role'], u['bus'], dr[0], dr[1])
        phone_map = {p['name']: p.get('phone', '') for p in provs}

        # --- LÓGICA POR ROLES ---
        
        # 1. ROL CONDUCTOR
        if u['role'] == 'driver':
            st.subheader("⛽ Carga de Combustible")
            with st.form("fuel_driver_main"):
                c1, c2, c3 = st.columns(3)
                k = c1.number_input("KM Actual", min_value=0)
                g = c2.number_input("Galones", min_value=0.0)
                c = c3.number_input("$ Total", min_value=0.0)
                if st.form_submit_button("🚀 GUARDAR COMBUSTIBLE", type="primary", use_container_width=True):
                    if k > 0 and g > 0 and c > 0:
                        REFS["data"].collection("logs").add({
                            "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                            "category": "Combustible", "km_current": k, "gallons": g, "com_cost": c, "com_paid": c
                        })
                        st.cache_data.clear()
                        st.success("Registrado con éxito"); time.sleep(1); st.rerun()
            st.divider()
            menu = {
                "🏠 Radar de Unidad": lambda: render_radar(df, u),
                "💰 Pagos y Abonos": lambda: render_accounting(df, u, phone_map),
                "📊 Mis Reportes": lambda: render_reports(df),
                "🛠️ Reportar Taller": lambda: render_workshop(u, provs),
                "🏢 Directorio": lambda: render_directory(provs, u)
            }
            choice = st.sidebar.radio("Más opciones:", list(menu.keys()))
            menu[choice]()

        # 2. ROL MECÁNICO
        elif u['role'] == 'mechanic':
            st.subheader(f"🛠️ Centro de Servicio: {u['name']}")
            buses_disponibles = sorted(df['bus'].unique()) if not df.empty else ["Sin Unidades"]
            bus_sel = st.sidebar.selectbox("Unidad a Reparar", buses_disponibles)
            df_bus = df[df['bus'] == bus_sel] if not df.empty else df

            menu = {
                "📝 Registrar Trabajo": lambda: render_mechanic_work(u, bus_sel, provs),
                "🏠 Estado del Bus": lambda: render_radar(df_bus, u),
                "📊 Historial Técnico": lambda: render_reports(df_bus),
                "🏢 Directorio": lambda: render_directory(provs, u)
            }
            choice = st.sidebar.radio("Menú Mecánico:", list(menu.keys()))
            menu[choice]()

        # 3. ROL DUEÑO (Un solo bloque else)
        else:
            render_radar(df, u)
            st.divider()
            menu = {
                "⛽ Combustible": lambda: render_fuel(), 
                "📊 Reportes": lambda: render_reports(df),
                "🛠️ Taller": lambda: render_workshop(u, provs),
                "💰 Contabilidad": lambda: render_accounting(df, u, phone_map),
                "🏢 Directorio": lambda: render_directory(provs, u),
                "👥 Personal": lambda: render_personnel(u),
                "🚛 Gestión": lambda: render_fleet_management(df, u),
                "🧠 Entrenar IA": lambda: render_ai_training(u)
            }
            choice = st.sidebar.radio("Ir a:", list(menu.keys()))
            menu[choice]()
        
        # Sidebar final
        st.sidebar.divider()
        if st.sidebar.button("Cerrar Sesión", use_container_width=True): 
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
