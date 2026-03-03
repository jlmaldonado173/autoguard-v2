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

# --- 1. CONFIGURACIÓN Y ESTILOS ---
APP_CONFIG = {
    "APP_ID": "itero-titanium-v15",
    "MASTER_KEY": "ADMIN123",
    "VERSION": "10.5.0 Itero Master AI", 
    "LOGO_URL": "Gemini_Generated_Image_buyjdmbuyjdmbuyj.png", 
    "BOSS_PHONE": "0999999999" 
}

UI_COLORS = {
    "primary": "#1E1E1E",
    "danger": "#FF4B4B",
    "success": "#28a745",
    "warning": "#ffc107",
    "bg_metric": "#f8f9fa"
}

st.set_page_config(page_title="Itero", layout="wide", page_icon="🚛")

st.markdown("""
    <style>
    .main-title { font-size: 65px; font-weight: 900; background: linear-gradient(45deg, #1E1E1E, #4A4A4A); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 20px; }
    .stButton>button { width: 100%; border-radius: 12px; border: none; padding: 12px 20px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); color: #1E1E1E; font-weight: 700; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: all 0.3s ease; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e0 100%); }
    div.stButton > button:first-child[kind="primary"] { background: linear-gradient(135deg, #1e1e1e 0%, #434343 100%); color: white; }
    .btn-whatsapp { display: inline-block; background: linear-gradient(135deg, #25D366 0%, #128C7E 100%); color: white !important; text-decoration: none; padding: 15px 25px; border-radius: 12px; font-weight: 800; text-align: center; width: 100%; box-shadow: 0 4px 15px rgba(37, 211, 102, 0.3); transition: all 0.3s ease; border: none; }
    .btn-whatsapp:hover { transform: scale(1.02); box-shadow: 0 6px 20px rgba(37, 211, 102, 0.4); }
    .metric-box { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; }
    </style>
    """, unsafe_allow_html=True)

# --- UTILERÍAS ---
def format_phone(phone):
    if not phone: return ""
    p = str(phone).replace(" ", "").replace("+", "").replace("-", "")
    if p.startswith("0"): return "593" + p[1:]  
    if not p.startswith("593"): return "593" + p 
    return p

# --- 2. CONFIGURACIÓN DE IA ---
try:
    if "GEMINI_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_KEY"]["api_key"])
        HAS_AI = True
    else:
        HAS_AI = False
except Exception:
    HAS_AI = False

@st.cache_resource
def get_ai_model():
    if not HAS_AI: return None
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        model_name = next((m for m in valid_models if "1.5-flash" in m), valid_models[0] if valid_models else "models/gemini-1.5-flash")
        return genai.GenerativeModel(model_name)
    except Exception:
        return None

def get_ai_analysis(df_bus, bus_id, fleet_id):
    if not HAS_AI: return "⚠️ IA no disponible."
    model = get_ai_model()
    if not model: return "Error de conexión IA."
    
    try:
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
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error en análisis IA: {str(e)}"

# --- 3. CAPA DE DATOS ---
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

        # --- MEJORA: Añadimos 'status' y 'driver_feedback' a las columnas permitidas ---
        cols_config = {'bus': '0', 'category': '', 'observations': '', 'km_current': 0, 'km_next': 0, 'mec_cost': 0, 'com_cost': 0, 'mec_paid': 0, 'com_paid': 0, 'gallons': 0, 'status': 'completed', 'driver_feedback': ''}
        
        if not logs: return provs, pd.DataFrame(columns=list(cols_config.keys()) + ['date'])
        
        df = pd.DataFrame(logs)
        for col, val in cols_config.items():
            if col not in df.columns: df[col] = val
            if isinstance(val, (int, float)): df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, df
    except Exception as e:
        st.error(f"Error: {e}"); return [], pd.DataFrame()

# --- 4. UI LOGIN Y SUPER ADMIN ---
def ui_render_login():
    st.markdown('<div class="main-title">Itero AI</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["👤 Ingresar", "📝 Crear Flota", "⚙️ Super Admin"])

    with t1:
        with st.container(border=True):
            col1, col2 = st.columns(2)
            f_in = col1.text_input("Código de Flota").upper().strip()
            u_in = col2.text_input("Usuario").upper().strip()
            
            r_in = st.selectbox("Perfil", ["Conductor", "Mecánico", "Administrador/Dueño"])
            
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
    
    if data.get('status') == 'suspended':
        sup_snap = REFS["data"].get()
        contacto_maestro = "jlmaldonado173@gmail.com o 0964014007"
        contacto = sup_snap.to_dict().get("support_contact", contacto_maestro) if sup_snap.exists else contacto_maestro
        
        st.warning(f"""
            ### ℹ️ Aviso de Cuenta
            Estimado usuario, su acceso a **Itero AI** se encuentra temporalmente inactivo. 
            Para reactivar sus servicios, le invitamos cordialmente a ponerse en contacto con nuestra administración:
            📧 **{contacto}**
        """)
        return

    access = False; role = ""; assigned_bus = "0"
    
    if "Adm" in r_in:
        if data.get('password') == pass_in: 
            access = True; role = 'owner'
        else: 
            st.error("🔒 Contraseña incorrecta.")
    else:
        auth = REFS["fleets"].document(f_in).collection("authorized_users").document(u_in).get()
        
        if auth.exists and auth.to_dict().get('active', True): 
            user_data = auth.to_dict()
            db_role = user_data.get('role', 'driver')
            assigned_bus = user_data.get('bus', '0')
            
            if "Mec" in r_in:
                if db_role == 'mechanic':
                    access = True; role = 'mechanic'
                else:
                    st.error("❌ Acceso denegado: Este usuario no está registrado como Mecánico.")
            elif "Cond" in r_in:
                if db_role == 'driver':
                    access = True; role = 'driver'
                else:
                    st.error("❌ Acceso denegado: Este usuario no está registrado como Conductor.")
        else: 
            st.error("❌ Usuario no autorizado. Verifique que el nombre esté escrito exactamente igual.")

    if access:
        st.session_state.user = {'role': role, 'fleet': f_in, 'name': u_in, 'bus': assigned_bus}
        st.rerun()

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
    
    with st.expander("🛠️ Configuración de Mensaje de Bloqueo", expanded=True):
        msg_default = "jlmaldonado173@gmail.com o llame al 0964014007"
        doc_snap = REFS["data"].get()
        current_msg = doc_snap.to_dict().get("support_contact", msg_default) if doc_snap.exists else msg_default
        c_msg = st.text_input("Contacto de soporte para flotas suspendidas", value=current_msg)
        
        if st.button("Guardar Contacto Maestro"):
            REFS["data"].set({"support_contact": c_msg}, merge=True)
            st.success("✅ ¡Contacto guardado!")

    st.subheader("🏢 Gestión de Empresas Registradas")
    
    for f in REFS["fleets"].stream():
        d = f.to_dict()
        unidades = REFS["data"].collection("logs").where("fleetId", "==", f.id).stream()
        bus_list = set([u.to_dict().get('bus') for u in unidades if u.to_dict().get('bus')])
        total_buses = len(bus_list)

        with st.expander(f"Empresa: {f.id} | Dueño: {d.get('owner')} | 🚛 {total_buses} Unidades", expanded=False):
            c1, c2, c3 = st.columns(3)
            
            is_active = d.get('status') == 'active'
            label = "🔴 SUSPENDER" if is_active else "🟢 ACTIVAR"
            if c1.button(label, key=f"s_{f.id}"):
                REFS["fleets"].document(f.id).update({"status": "suspended" if is_active else "active"})
                st.rerun()
            
            new_pass = c2.text_input("Nueva Clave", key=f"p_{f.id}", type="password")
            if c2.button("Cambiar Password", key=f"bp_{f.id}"):
                if new_pass:
                    REFS["fleets"].document(f.id).update({"password": new_pass})
                    st.success("🔑 Clave actualizada")
                else: 
                    st.error("Escribe una clave")

            if c3.button("🗑️ ELIMINAR FLOTA", key=f"del_{f.id}"):
                REFS["fleets"].document(f.id).delete()
                st.rerun()

# --- 5. VISTAS PRINCIPALES ---
def render_radar(df, user):
    st.subheader("📡 Radar de Flota")
    if df.empty or 'bus' not in df.columns: 
        st.info("⏳ Sin datos actuales."); return

    buses = sorted(df['bus'].unique()) if user['role'] == 'owner' else [user['bus']]
    
    for bus in buses:
        bus_df = df[df['bus'] == bus].sort_values('date', ascending=False)
        if bus_df.empty: continue
        
        # 1. Obtener KM Actual
        latest = bus_df.iloc[0]
        km_actual = latest['km_current']
        
        # 2. Obtener KM del Próximo Cambio de Aceite
        oil_records = bus_df[bus_df['category'] == "Aceite Motor"].sort_values('date', ascending=False)
        km_proximo_aceite = oil_records.iloc[0].get('km_next', 0) if not oil_records.empty else 0

        # 3. Lógica de Alerta (Solo si faltan 500 KM o menos)
        faltan_para_cambio = km_proximo_aceite - km_actual
        es_alerta = 0 < faltan_para_cambio <= 500
        es_vencido = km_actual >= km_proximo_aceite and km_proximo_aceite > 0

        # 4. Definir Color de Tarjeta
        if es_vencido:
            bg_color = "linear-gradient(135deg, #FF4B4B 0%, #8B0000 100%)" # Rojo
            msg = "🚨 VENCIDO: Aceite Motor"
        elif es_alerta:
            bg_color = "linear-gradient(135deg, #ffc107 0%, #e67e22 100%)" # Naranja
            msg = "⚠️ PRÓXIMO: Aceite Motor"
        else:
            bg_color = "linear-gradient(135deg, #28a745 0%, #1e7e34 100%)" # Verde
            msg = "✅ UNIDAD OPERATIVA"

        # 5. Renderizado Visual (Tarjeta)
        st.markdown(f"""
            <div style="background:{bg_color}; padding:25px; border-radius:15px; color:white; margin-bottom:10px;">
                <h2 style="margin:0;">BUS {bus}</h2>
                <p style="margin:0; font-weight:bold;">{msg}</p>
                <div style="display:flex; justify-content:space-between; margin-top:15px; background:rgba(255,255,255,0.1); padding:10px; border-radius:10px;">
                    <div style="text-align:center;">
                        <small>ACTUAL</small><br>
                        <b style="font-size:20px;">{km_actual:,.0f}</b>
                    </div>
                    <div style="text-align:center;">
                        <small>PRÓXIMO</small><br>
                        <b style="font-size:20px;">{km_proximo_aceite:,.0f}</b>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Botón de IA y Notificación
        if user['role'] == 'owner':
            if st.button(f"🤖 Diagnóstico IA {bus}", key=f"ai_{bus}"):
                st.info(get_ai_analysis(bus_df, bus, user['fleet']))
        else:
            if es_alerta or es_vencido:
                wa_msg = f"Jefe, el Bus {bus} está {msg}. Actual: {km_actual} / Próximo: {km_proximo_aceite}"
                link = f"https://wa.me/{format_phone(APP_CONFIG['BOSS_PHONE'])}?text={urllib.parse.quote(wa_msg)}"
                st.markdown(f'<a href="{link}" target="_blank" class="btn-whatsapp">📲 NOTIFICAR AL JEFE</a>', unsafe_allow_html=True)

def render_ai_training(user):
    st.header("🧠 Entrenar Inteligencia Artificial")
    st.info("Escribe aquí las reglas personalizadas para tu flota (Ej: 'Alerta si el cambio de aceite supera los 10,000km' o 'El Bus 05 siempre gasta más diesel').")

    # 1. Recuperar las reglas actuales de la base de datos para que aparezcan al abrir
    doc_ref = REFS["fleets"].document(user['fleet'])
    doc = doc_ref.get()
    
    current_rules = ""
    if doc.exists:
        current_rules = doc.to_dict().get("ai_rules", "")

    # 2. Formulario de edición
    with st.form("ai_training_form"):
        # El text_area muestra lo que ya está guardado (current_rules)
        new_rules = st.text_area(
            "Reglas y Parámetros de la Flota:", 
            value=current_rules, 
            height=300,
            help="Estas reglas guiarán el diagnóstico de la IA cuando presiones el botón de 'Analizar' en el Radar."
        )
        
        submit_btn = st.form_submit_button("💾 GUARDAR Y ACTUALIZAR IA", type="primary")

        if submit_btn:
            try:
                # 3. Guardar en Firebase con merge=True para no borrar otros datos (como la clave)
                doc_ref.set({"ai_rules": new_rules}, merge=True)
                
                # 4. MENSAJE DE ÉXITO VISUAL
                st.success("✅ ¡Reglas guardadas! La IA ahora usará estas instrucciones para analizar tu flota.")
                st.balloons() # Efecto visual de éxito
                
                # Limpiamos cache para que la IA use las nuevas reglas de inmediato
                st.cache_data.clear()
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    # Mostrar un resumen de lo que la IA sabe actualmente
    if current_rules:
        st.caption("✨ Actualmente la IA está entrenada con tus reglas personalizadas.")
    else:
        st.warning("⚠️ La IA está usando parámetros genéricos. Escribe tus reglas arriba para personalizarla.")
def display_top_notifications(user):
    """Muestra una alerta en la parte superior si el usuario tiene mensajes sin leer"""
    if not REFS: return
    # Busca notificaciones dirigidas al rol actual (ej. owner, driver, mechanic)
    notifs = REFS["data"].collection("notifications").where("fleetId", "==", user['fleet']).where("target_role", "==", user['role']).where("status", "==", "unread").stream()
    
    lista_notifs = [{"id": n.id, **n.to_dict()} for n in notifs]
    
    if lista_notifs:
        st.error(f"🔔 TIENES {len(lista_notifs)} NOTIFICACIÓN(ES) NUEVA(S)")
        for n in lista_notifs:
            with st.container(border=True):
                st.write(f"📩 **De:** {n.get('sender')} | 📅 {n.get('date', '')[:10]}")
                st.info(f"💬 {n.get('message', '')}")
                if st.button("✅ Marcar como leído", key=f"read_{n['id']}"):
                    REFS["data"].collection("notifications").document(n['id']).update({"status": "read"})
                    st.rerun()
        st.divider()

def render_communications(user):
    """Módulo completo para enviar mensajes entre roles"""
    st.header("💬 Centro de Mensajes y Alertas")
    
    with st.form("send_message_form", clear_on_submit=True):
        st.subheader("📤 Redactar Nueva Alerta")
        
        # Opciones de a quién enviarlo
        roles = {"Administrador/Dueño": "owner", "Mecánicos": "mechanic", "Conductores": "driver"}
        destino = st.selectbox("Enviar a todos los:", list(roles.keys()))
        mensaje = st.text_area("Escribe tu mensaje o reporte:")
        
        c1, c2 = st.columns(2)
        btn_app = c1.form_submit_button("🔔 Enviar Notificación por App", type="primary")
        btn_wa = c2.form_submit_button("📲 Preparar para WhatsApp", type="secondary")
        
        if btn_app:
            if mensaje:
                REFS["data"].collection("notifications").add({
                    "fleetId": user['fleet'],
                    "sender": f"{user['name']} ({user['role'].upper()})",
                    "target_role": roles[destino],
                    "message": mensaje,
                    "date": get_current_time(),
                    "status": "unread"
                })
                st.success(f"✅ Notificación enviada al sistema de los {destino}.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Por favor, escribe un mensaje.")
                
        if btn_wa:
            if mensaje:
                if roles[destino] == "owner":
                    # Si va al administrador, usa el número del sistema
                    link = f"https://wa.me/{format_phone(APP_CONFIG['BOSS_PHONE'])}?text={urllib.parse.quote(mensaje)}"
                    st.markdown(f'<a href="{link}" target="_blank" class="btn-whatsapp">📲 Enviar WhatsApp al Administrador</a>', unsafe_allow_html=True)
                else:
                    st.info("💡 Para contactar por WhatsApp a un empleado específico, usa los botones en el 'Directorio' o 'Personal'. (La notificación por App sí se puede enviar masivamente).")

def render_reports(df, user):
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
        st.subheader("🚦 Estado de Mantenimientos")
        # Obtenemos el KM máximo reportado para cada bus
        km_reales = df.groupby('bus')['km_current'].max()
        mantenimientos = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
        
        datos_estado = []
        for _, r in mantenimientos.iterrows():
            bus = r['bus']
            km_actual_real = km_reales.get(bus, r['km_current'])
            km_meta = r['km_next']
            faltan = km_meta - km_actual_real
            
            if faltan < 0: estado = "🔴 VENCIDO"
            elif faltan <= 500: estado = f"🟡 PRÓXIMO ({faltan:,.0f} km)"
            else: estado = f"🟢 OK (faltan {faltan:,.0f} km)"
                
            datos_estado.append({
                "Bus": bus, "Categoría": r['category'], "Estado": estado,
                "KM Actual": km_actual_real, "Próximo Cambio": km_meta
            })
            
        if datos_estado:
            st.dataframe(pd.DataFrame(datos_estado).sort_values(['Bus', 'Categoría']), use_container_width=True, hide_index=True)
        else:
            st.info("No hay mantenimientos programados con kilometraje a futuro.")

    with t3:
        st.subheader("📜 Bitácora de Movimientos (EDICIÓN)")
        df_sorted = df.sort_values('date', ascending=False)
        
        for _, r in df_sorted.iterrows():
            fecha_str = r['date'].strftime('%d/%m/%Y %H:%M')
            with st.expander(f"📅 {fecha_str} | Bus {r['bus']} | {r['category']} | KM: {r['km_current']:,.0f}"):
                col_txt, col_img = st.columns([2, 1])
                
                with col_txt:
                    st.write(f"**Detalle:** {r.get('observations', 'Sin detalle')}")
                    st.write(f"**KM Actual Guardado:** {r['km_current']:,.0f}")
                    if r.get('km_next', 0) > 0:
                        st.write(f"**Próximo Programado:** {r['km_next']:,.0f}")
                    
                    if r.get('mec_name') and r['mec_name'] != "N/A":
                        st.caption(f"👨‍🔧 Mecánico: {r['mec_name']} (${r.get('mec_cost', 0)})")
                    if r.get('com_name') and r['com_name'] != "N/A":
                        st.caption(f"🛒 Comercio: {r['com_name']} (${r.get('com_cost', 0)})")
                        
                    st.divider()
                    
                    # --- LÓGICA DE EDICIÓN SEGÚN ROL ---
                    if user['role'] == 'owner':
                        edit_mode = st.checkbox(f"✏️ Editar / Corregir este registro", key=f"edit_check_{r['id']}")
                        if edit_mode:
                            with st.form(f"form_edit_{r['id']}"):
                                st.warning("Modifica los valores y guarda.")
                                new_ka = st.number_input("Corregir KM Actual", value=int(r['km_current']), step=1)
                                new_kn = st.number_input("Corregir Próximo (KM Meta)", value=int(r.get('km_next', 0)), step=1)
                                new_obs = st.text_area("Corregir Detalle", value=r.get('observations', ''))
                                
                                col_btn1, col_btn2 = st.columns(2)
                                if col_btn1.form_submit_button("💾 Guardar Cambios", type="primary"):
                                    REFS["data"].collection("logs").document(r['id']).update({
                                        "km_current": new_ka,
                                        "km_next": new_kn,
                                        "observations": new_obs
                                    })
                                    st.cache_data.clear()
                                    st.success("✅ Registro actualizado.")
                                    time.sleep(1)
                                    st.rerun()
                                    
                        # Botón de borrar para el dueño
                        if st.button("🗑️ Eliminar Reporte", key=f"del_rep_{r['id']}"):
                            REFS["data"].collection("logs").document(r['id']).delete()
                            st.cache_data.clear()
                            st.rerun()
                            
                    elif user['role'] in ['driver', 'mechanic']:
                        st.info("💡 ¿Hay algún error en este registro?")
                        
                        # Caja de texto para que el usuario explique el problema
                        explicacion = st.text_area(
                            "Explica qué está mal y cuál es el dato correcto:", 
                            placeholder="Ej: Me equivoqué de categoría, era Suspensión. / El kilometraje correcto es 365000.",
                            key=f"exp_{r['id']}"
                        )
                        
                        col_wa, col_app = st.columns(2)
                        
                        # 1. Botón de Notificación Interna (App)
                        if col_app.button("🔔 Enviar Solicitud por App", key=f"req_edit_{r['id']}", use_container_width=True):
                            if explicacion.strip() == "":
                                st.error("❌ Por favor, escribe tu explicación antes de enviar.")
                            else:
                                from datetime import datetime
                                REFS["data"].collection("notifications").add({
                                    "fleetId": user['fleet'],
                                    "sender": f"{user['name']} ({user['role'].upper()})",
                                    "target_role": "owner",
                                    "message": f"🚩 SOLICITUD DE CORRECCIÓN (Bus {r['bus']} | {r['category']}): {explicacion}",
                                    "date": datetime.now().isoformat(),
                                    "status": "unread"
                                })
                                st.success("✅ Explicación enviada al Administrador con éxito.")
                        
                        # 2. Botón de WhatsApp (Avisa que revisen la app)
                        wa_text = f"Hola Administrador, necesito corregir el reporte del *Bus {r['bus']}* ({r['category']}) del *{fecha_str}*. Ya te envié la explicación detallada por la campana de notificaciones de la App. ¡Por favor revísalo cuando puedas!"
                        wa_link = f"https://wa.me/{format_phone(APP_CONFIG['BOSS_PHONE'])}?text={urllib.parse.quote(wa_text)}"
                        
                        col_wa.markdown(f'<a href="{wa_link}" target="_blank" class="btn-whatsapp" style="padding:10px; font-size:14px; text-align:center; display:block;">📲 Avisar por WhatsApp</a>', unsafe_allow_html=True)
                
                with col_img:
                    if "photo_b64" in r and r["photo_b64"]:
                        try:
                            st.image(f"data:image/jpeg;base64,{r['photo_b64']}", use_container_width=True)
                        except:
                            st.error("Error visualizando foto")
def render_accounting(df, user, phone_map):
    st.header("💰 Contabilidad y Abonos")
    
    pend = df[(df['mec_cost'] > df['mec_paid']) | (df['com_cost'] > df['com_paid'])]
    
    if pend.empty:
        st.success("🎉 Todo al día. No hay deudas pendientes.")
        return
    
    for bus in sorted(pend['bus'].unique()):
        with st.expander(f"🚌 DEUDAS BUS {bus}", expanded=True):
            bus_pend = pend[pend['bus'] == bus].sort_values('date', ascending=False)
            
            for _, r in bus_pend.iterrows():
                st.markdown(f"""
                <div class="metric-box" style="margin-bottom:15px;">
                    <p style="margin:0; color:#666; font-size:12px;">{r['date'].strftime('%d-%m-%Y')}</p>
                    <h4 style="margin:0 0 10px 0;">{r['category']}</h4>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                
                deudas = [
                    ('m', 'mec_cost', 'mec_paid', 'mec_name', '👨‍🔧 Mano de Obra'),
                    ('c', 'com_cost', 'com_paid', 'com_name', '🛒 Repuestos/Comercio')
                ]
                
                for t, cost, paid, name, lbl in deudas:
                    debt = r[cost] - r[paid]
                    col = c1 if t == 'm' else c2
                    
                    if debt > 0:
                        with col:
                            st.metric(lbl, f"${debt:,.2f}", help=f"Proveedor: {r.get(name,'No asignado')}")
                            
                            if user['role'] == 'owner':
                                v = st.number_input(
                                    f"Abonar a {r.get(name,'')}", 
                                    key=f"in_{t}{r['id']}", 
                                    max_value=float(debt), 
                                    min_value=0.0,
                                    step=10.0
                                )
                                
                                if st.button(f"Registrar Pago", key=f"btn_{t}{r['id']}", type="primary", use_container_width=True):
                                    REFS["data"].collection("logs").document(r['id']).update({
                                        paid: firestore.Increment(v)
                                    })
                                    
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
                                        
                                        st.markdown(f"""
                                            <a href="{link}" target="_blank" class="btn-whatsapp" style="text-decoration:none;">
                                                📲 ENVIAR COMPROBANTE WHATSAPP
                                            </a>
                                            <br>
                                        """, unsafe_allow_html=True)
                                    
                                    st.success(f"Abono de ${v} registrado.")
                                    st.cache_data.clear()
                                    time.sleep(2)
                                    st.rerun()
                st.markdown("---")

def render_workshop(user, providers):
    st.header("🛠️ Registro de Taller")
    
    fecha_registro = datetime.now().isoformat()
    mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    st.write("📸 **Foto del trabajo o factura (Opcional)**")
    foto_archivo = st.camera_input("Capturar evidencia", key=f"cam_{user.get('bus', 'default')}")
    
    with st.form("workshop_form_data"):
        tp = st.radio("Tipo", ["Preventivo", "Correctivo"], horizontal=True)
        
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Otro"])
        obs = st.text_area("Detalle")
        
        ka = c1.number_input("KM Actual", min_value=0)
        kn = c2.number_input("Próximo", min_value=ka) if tp == "Preventivo" else 0
        
        st.divider()
        col_m, col_r = st.columns(2)
        
        mn = col_m.selectbox("Mecánico", ["N/A"] + mecs)
        mc = col_m.number_input("Mano Obra $", min_value=0.0)
        mp = col_m.number_input("Abono MO $", min_value=0.0) 
        
        rn = col_r.selectbox("Comercio", ["N/A"] + coms)
        rc = col_r.number_input("Repuestos $", min_value=0.0)
        rp = col_r.number_input("Abono Rep $", min_value=0.0)
        
        enviar = st.form_submit_button("💾 GUARDAR REGISTRO", type="primary", use_container_width=True)
        
        if enviar:
            if ka <= 0:
                st.error("❌ ERROR: El kilometraje debe ser mayor a 0.")
            else:
                base64_photo = ""
                if foto_archivo:
                    base64_photo = base64.b64encode(foto_archivo.getvalue()).decode()
                
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": user['bus'],
                    "date": fecha_registro,
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
                    "photo_b64": base64_photo,
                    "status": "completed"
                })
                
                st.cache_data.clear()
                st.success("✅ ¡Registro guardado con éxito!")
                time.sleep(1)
                st.rerun()

def render_fuel():
    u = st.session_state.user
    st.header("⛽ Registro de Combustible")
    
    fecha_actual = datetime.now().isoformat()
    
    with st.form("fuel_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        k = c1.number_input("Kilometraje Actual", min_value=0)
        g = c2.number_input("Galones", min_value=0.0)
        c = c3.number_input("Costo Total $", min_value=0.0)
        
        if st.form_submit_button("🚀 REGISTRAR CARGA", type="primary", use_container_width=True):
            if k > 0 and g > 0 and c > 0:
                REFS["data"].collection("logs").add({
                    "fleetId": u['fleet'],
                    "bus": u['bus'],
                    "date": fecha_actual,
                    "category": "Combustible",
                    "km_current": k,
                    "gallons": g,
                    "com_cost": c,
                    "com_paid": c 
                })
                
                st.cache_data.clear() 
                st.success("✅ Carga registrada correctamente")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Por favor, llena todos los campos con valores mayores a 0.")

def render_personnel(user):
    st.header("👥 Gestión de Personal")
    
    with st.expander("➕ Registrar Nuevo Personal"):
        with st.form("nd"):
            nm = st.text_input("Nombre / Usuario").upper()
            te = st.text_input("Teléfono")
            rol = st.selectbox("Rol", ["driver", "mechanic"], format_func=lambda x: "🚛 Conductor" if x == "driver" else "🛠️ Mecánico")
            bs = st.text_input("Bus Asignado (Poner 0 para Mecánicos)")
            
            if st.form_submit_button("Crear Usuario", type="primary"):
                if nm:
                    REFS["fleets"].document(user['fleet']).collection("authorized_users").document(nm).set({
                        "active": True,
                        "phone": te,
                        "bus": bs,
                        "role": rol 
                    })
                    st.cache_data.clear()
                    st.success(f"Usuario {nm} creado como {rol}")
                    st.rerun()
                else:
                    st.error("El nombre es obligatorio")

    st.divider()
    st.subheader("📋 Lista de Personal Autorizado")

    usuarios = REFS["fleets"].document(user['fleet']).collection("authorized_users").stream()
    
    for us in usuarios:
        d = us.to_dict()
        if d.get('role') != 'owner' and d.get('role') != 'admin':
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                
                emoji = "🛠️" if d.get('role') == 'mechanic' else "🚛"
                c1.markdown(f"{emoji} **{us.id}**")
                c1.caption(f"Rol: {d.get('role')} | 📱 {d.get('phone')}")
                
                nb = c2.text_input("Unidad", value=d.get('bus',''), key=f"b_{us.id}")
                
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
    
    with st.expander("📱 Configuración de Alertas (WhatsApp del Dueño)", expanded=True):
        st.info("Ingresa el número donde recibirás las alertas de mantenimientos vencidos de tus conductores.")
        
        fleet_doc = REFS["fleets"].document(user['fleet']).get()
        current_phone = fleet_doc.to_dict().get("boss_phone", "") if fleet_doc.exists else ""
        
        col_w1, col_w2 = st.columns([3, 1])
        new_phone = col_w1.text_input("Tu número de WhatsApp (Ej: 0991234567)", value=current_phone)
        
        if col_w2.button("💾 Guardar Número", use_container_width=True):
            if new_phone:
                REFS["fleets"].document(user['fleet']).update({"boss_phone": new_phone})
                st.success("✅ Número actualizado. Las alertas llegarán aquí.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Por favor ingresa un número válido.")
    
    st.divider()

    buses = sorted(df['bus'].unique()) if 'bus' in df.columns and not df.empty else []
    c1, c2 = st.columns(2)
    
    with c1.container(border=True):
        st.subheader("✏️ Renombrar Unidad")
        if buses:
            old = st.selectbox("Unidad", buses, key="ren_old")
            new = st.text_input("Nuevo Nombre/Número")
            if st.button("Actualizar Nombre") and new:
                for d in REFS["data"].collection("logs").where("fleetId","==",user['fleet']).where("bus","==",old).stream():
                    REFS["data"].collection("logs").document(d.id).update({"bus": new})
                st.cache_data.clear()
                st.success("Nombre actualizado"); st.rerun()
        else:
            st.warning("No tienes unidades registradas aún.")

    with c2.container(border=True):
        st.subheader("🗑️ Borrar Historial")
        if buses:
            dbus = st.selectbox("Eliminar unidad", buses, key="del_bus")
            if st.button("ELIMINAR TODO EL HISTORIAL", type="secondary"):
                docs = REFS["data"].collection("logs").where("fleetId","==",user['fleet']).where("bus","==",dbus).stream()
                for d in docs:
                    REFS["data"].collection("logs").document(d.id).delete()
                
                st.cache_data.clear() 
                st.success(f"✅ Historial de la unidad {dbus} borrado por completo")
                time.sleep(1) 
                st.rerun()
        else:
            st.warning("No hay historiales para eliminar.")

    st.divider()

    st.subheader("🚀 Transferencia Directa a otro Dueño Itero")
    st.info("Esta función copia todo el historial de un bus a otra empresa Itero usando su Código de Flota.")
    
    if buses:
        col_t1, col_t2 = st.columns(2)
        target_fleet = col_t1.text_input("Código de Flota Destino").upper().strip()
        bus_to_send = col_t2.selectbox("Bus a transferir", buses, key="send_bus")
        
        if st.button("Realizar Transferencia Directa", type="primary"):
            if not target_fleet:
                st.error("Debes ingresar el código de la flota destino.")
            elif target_fleet == user['fleet']:
                st.error("No puedes transferir datos a tu propia flota.")
            else:
                dest_doc = REFS["fleets"].document(target_fleet).get()
                if dest_doc.exists:
                    logs_to_transfer = REFS["data"].collection("logs")\
                        .where("fleetId", "==", user['fleet'])\
                        .where("bus", "==", bus_to_send).stream()
                    
                    count = 0
                    for doc in logs_to_transfer:
                        data = doc.to_dict()
                        data['fleetId'] = target_fleet
                        data['observations'] = f"{data.get('observations', '')} (Importado de {user['fleet']})"
                        
                        REFS["data"].collection("logs").add(data)
                        count += 1
                    
                    if count > 0:
                        st.success(f"✅ ¡Transferencia Exitosa! Se enviaron {count} registros al código {target_fleet}.")
                        st.balloons()
                        msg_wa = f"Hola, te he transferido el historial de mi Bus {bus_to_send} a tu sistema Itero AI. ¡Ya puedes revisarlo!"
                        st.markdown(f"[📲 Notificar al nuevo dueño por WhatsApp](https://wa.me/?text={urllib.parse.quote(msg_wa)})")
                    else:
                        st.warning("No se encontraron registros para este bus.")
                else:
                    st.error(f"❌ La flota '{target_fleet}' no existe. Verifica el código con el nuevo dueño.")
    else:
        st.warning("Necesitas tener unidades con historial antes de poder transferirlas.")

def render_directory(providers, user):
    st.header("🏢 Directorio de Proveedores")
    
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

    # --- MEJORA: Separar la lista lógicamente ---
    mecanicos = [p for p in providers if p['type'] in ["Mecánico", "Electricista"]]
    comercios = [p for p in providers if p['type'] not in ["Mecánico", "Electricista"]]

    t1, t2 = st.tabs(["👨‍🔧 Mecánicos y Especialistas", "🛒 Comercios y Repuestos"])

    # Función interna para no repetir el código de las tarjetas
    def mostrar_lista(lista):
        if not lista:
            st.info("No hay registros en esta categoría.")
            return
            
        for p in lista:
            p_id = p.get('id')
            with st.container(border=True):
                col_info, col_wa = st.columns([2, 1])
                
                col_info.markdown(f"**{p['name']}**")
                col_info.caption(f"🔧 {p['type']} | 📞 {p.get('phone', 'S/N')}")
                
                if p.get('phone'):
                    ph = "".join(filter(str.isdigit, p['phone']))
                    if ph.startswith('0'): ph = '593' + ph[1:] 
                    
                    link = f"https://wa.me/{ph}?text=Hola%20{p['name']}"
                    col_wa.markdown(
                        f'<a href="{link}" target="_blank" style="text-decoration:none;">'
                        f'<div style="background-color:#25D366; color:white; padding:8px; border-radius:10px; text-align:center; font-weight:bold;">'
                        f'📲 CHAT</div></a>', 
                        unsafe_allow_html=True
                    )

                if user['role'] == 'owner':
                    st.divider()
                    c_edit, c_del = st.columns(2)
                    
                    edit_mode = c_edit.checkbox("✏️ Editar", key=f"ed_check_{p_id}")
                    
                    if c_del.button("🗑️ Eliminar", key=f"del_btn_{p_id}", use_container_width=True):
                        REFS["data"].collection("providers").document(p_id).delete()
                        st.cache_data.clear()
                        st.toast(f"Eliminado: {p['name']}")
                        time.sleep(0.5)
                        st.rerun()

                    if edit_mode:
                        with st.form(f"f_ed_{p_id}"):
                            new_n = st.text_input("Nombre", value=p['name']).upper()
                            new_p = st.text_input("WhatsApp", value=p.get('phone',''))
                            
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

    # Mostrar el contenido en cada pestaña
    with t1:
        mostrar_lista(mecanicos)
        
    with t2:
        mostrar_lista(comercios)
        
def render_mechanic_work(user, df, providers):
    st.header("🛠️ Registrar Trabajo Mecánico")
    
    buses_activos = set(df['bus'].unique()) if 'bus' in df.columns and not df.empty else set()
    
    try:
        usuarios = REFS["fleets"].document(user['fleet']).collection("authorized_users").stream()
        for us in usuarios:
            b = us.to_dict().get('bus', '0')
            if b != '0' and b: 
                buses_activos.add(b)
    except Exception:
        pass
        
    buses_disponibles = sorted(list(buses_activos)) if buses_activos else ["Sin Unidades"]
    
    bus_id = st.selectbox("🚛 Seleccionar Unidad a Reparar", buses_disponibles)
    
    # Mostrar último KM para ayudar al mecánico
    bus_df = df[df['bus'] == bus_id] if not df.empty and 'bus' in df.columns else pd.DataFrame()
    last_km = int(bus_df['km_current'].max()) if not bus_df.empty and 'km_current' in bus_df.columns else 0
    
    st.info(f"Registrando trabajo para la Unidad: **{bus_id}** | Último KM registrado: **{last_km:,.0f}**")
    
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    with st.form("mechanic_log"):
        cat = st.selectbox("Categoría del Daño", ["Mecánica", "Eléctrica", "Frenos", "Suspensión", "Motor", "Llantas", "Otro"])
        obs = st.text_area("Informe Técnico", placeholder="Describa el daño encontrado y la solución...")
        
        # --- SOLUCIÓN: Los campos siempre visibles ---
        st.divider()
        st.write("⏱️ **Control de Kilometraje y Alertas**")
        c_km1, c_km2 = st.columns(2)
        
        km_actual = c_km1.number_input("Kilometraje Actual del Bus", min_value=0, value=last_km, step=100)
        
        # El campo de aviso aparece siempre. Si no hay aviso, el mecánico lo deja en 0.
        km_proximo = c_km2.number_input("Avisar próximo a los (KM)", min_value=0, value=0, step=500, help="Ingresa a qué KM el radar se pondrá rojo. Deja en 0 si es un arreglo que no necesita aviso futuro.")
        
        st.divider()
        st.write("💰 **Costos y Repuestos**")
        c1, c2 = st.columns(2)
        mo_cost = c1.number_input("Costo Mano de Obra $", min_value=0.0)
        
        store_name = c2.selectbox("Comprado en:", ["N/A"] + coms)
        rep_cost = c2.number_input("Costo de Repuestos $", min_value=0.0)
        
        foto = st.camera_input("Capturar evidencia del trabajo", key=f"mech_cam_{bus_id}")
        
        if st.form_submit_button("ENVIAR REPORTE Y CARGAR A CONTABILIDAD", type="primary"):
            if not foto or not obs:
                st.error("Debe incluir descripción y foto de evidencia.")
            elif km_actual <= 0:
                st.error("❌ El kilometraje actual debe ser mayor a 0.")
            else:
                bytes_data = foto.getvalue()
                b64 = base64.b64encode(bytes_data).decode()
                
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": bus_id,
                    "date": datetime.now().isoformat(),
                    "category": cat,
                    "observations": f"REPORTE MECÁNICO ({user['name']}): {obs}",
                    "km_current": km_actual,  # <-- KM REAL
                    "km_next": km_proximo,    # <-- KM DE ALERTA (0 si no hay)
                    "mec_name": user['name'], 
                    "mec_cost": mo_cost,
                    "mec_paid": 0, 
                    "com_name": store_name,
                    "com_cost": rep_cost,
                    "com_paid": 0, 
                    "photo_b64": b64,
                    "status": "pending_driver",
                    "driver_feedback": ""
                })
                
                st.cache_data.clear()
                st.success("✅ Reporte enviado. Los radares han sido actualizados.")
                time.sleep(1)
                st.rerun()
def main():
    if 'user' not in st.session_state:
        ui_render_login()
    else:
        u = st.session_state.user
        
        if "LOGO_URL" in APP_CONFIG: 
            st.sidebar.image(APP_CONFIG["LOGO_URL"], width=200)
        st.sidebar.title(f"Itero: {u['name']}")
        
        dr = st.sidebar.date_input("Fechas", [date.today() - timedelta(days=90), date.today()])
        
        provs, df = fetch_fleet_data(u['fleet'], u['role'], u['bus'], dr[0], dr[1])
        phone_map = {p['name']: p.get('phone', '') for p in provs}

        # ---------------------------------------------------------
        # 🔔 CAMPANA DE NOTIFICACIONES (Se muestra arriba para todos)
        # ---------------------------------------------------------
        display_top_notifications(u)

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
                        st.success("Registrado con éxito")
                        time.sleep(1)
                        st.rerun()
            st.divider()
            
            # ---> MENÚ CONDUCTOR <---
            menu = {
                "🏠 Radar de Unidad": lambda: render_radar(df, u),
                "💰 Pagos y Abonos": lambda: render_accounting(df, u, phone_map),
                "📊 Reportes": lambda: render_reports(df, u), 
                "🛠️ Reportar Taller": lambda: render_workshop(u, provs),
                "💬 Mensajes": lambda: render_communications(u), # <--- NUEVO MÓDULO AÑADIDO
                "🏢 Directorio": lambda: render_directory(provs, u)
            }
            choice = st.sidebar.radio("Más opciones:", list(menu.keys()))
            menu[choice]()

        # 2. ROL MECÁNICO
        elif u['role'] == 'mechanic':
            st.subheader(f"🛠️ Centro de Servicio: {u['name']}")
            
            # ---> MENÚ MECÁNICO <---
            menu = {
                "🏠 Radar de Taller": lambda: render_radar(df, u),
                "📝 Registrar Trabajo": lambda: render_mechanic_work(u, df, provs),
                "📊 Historial Técnico Completo": lambda: render_reports(df, u), 
                "💬 Mensajes": lambda: render_communications(u), # <--- NUEVO MÓDULO AÑADIDO
                "🏢 Directorio": lambda: render_directory(provs, u)
            }
            choice = st.sidebar.radio("Menú Mecánico:", list(menu.keys()))
            menu[choice]()

        # 3. ROL DUEÑO / ADMINISTRADOR
        else:
            render_radar(df, u)
            st.divider()
            
            # ---> MENÚ DUEÑO <---
            menu = {
                "⛽ Combustible": lambda: render_fuel(), 
                "📊 Reportes": lambda: render_reports(df, u), 
                "🛠️ Taller": lambda: render_workshop(u, provs),
                "💰 Contabilidad": lambda: render_accounting(df, u, phone_map),
                "💬 Mensajes": lambda: render_communications(u), # <--- NUEVO MÓDULO AÑADIDO
                "🏢 Directorio": lambda: render_directory(provs, u),
                "👥 Personal": lambda: render_personnel(u),
                "🚛 Gestión": lambda: render_fleet_management(df, u),
                "🧠 Entrenar IA": lambda: render_ai_training(u)
            }
            choice = st.sidebar.radio("Ir a:", list(menu.keys()))
            menu[choice]()
        
        # --- BOTÓN DE SALIDA UNIFICADO ---
        st.sidebar.divider()
        if st.sidebar.button("Cerrar Sesión", use_container_width=True): 
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
