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
def draw_svg_gauge(categoria, faltan, meta):
    """Genera un reloj circular SVG. Maneja casos sin meta (Gris)."""
    radio = 40
    circunferencia = 2 * 3.14159 * radio
    
    # CASO 1: Mantenimiento sin meta programada
    if meta <= 0:
        porcentaje = 0
        color = "#555555" # Gris oscuro
        texto_estado = "SIN META"
        dash_offset = circunferencia # Reloj vacío
        texto_central = "- %"
        subtexto = "No programado"
        
    # CASO 2: Mantenimiento con meta (Matemática normal)
    else:
        # Si faltan < 0, está vencido (0% de vida útil)
        if faltan < 0:
            porcentaje = 0
            color = "#FF4B4B"  # Rojo
            texto_estado = "VENCIDO"
            texto_central = "0%"
        else:
            porcentaje = min(100, (faltan / meta) * 100)
            if faltan <= 1500:
                color = "#ffc107"  # Amarillo
                texto_estado = "PRÓXIMO"
            else:
                color = "#28a745"  # Verde
                texto_estado = "ÓPTIMO"
            texto_central = f"{int(porcentaje)}%"
            
        dash_offset = circunferencia - (porcentaje / 100) * circunferencia
        subtexto = f"Faltan: {faltan:,.0f} km"

    # Construcción visual del SVG
    svg_html = f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 15px 10px; background-color: #1E1E1E; border-radius: 15px; border: 1px solid {color}50; box-shadow: 0 6px 15px rgba(0,0,0,0.2); height: 100%;">
        <h4 style="color: white; margin-top: 0; margin-bottom: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; text-align: center;">{categoria}</h4>
        <svg width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="{radio}" stroke="#333333" stroke-width="8" fill="none" />
            <circle cx="50" cy="50" r="{radio}" stroke="{color}" stroke-width="8" fill="none" 
                    stroke-dasharray="{circunferencia}" stroke-dashoffset="{dash_offset}" 
                    stroke-linecap="round" transform="rotate(-90 50 50)" 
                    style="transition: stroke-dashoffset 1.5s ease-in-out;" />
            <text x="50" y="45" font-family="Arial" font-size="20" font-weight="bold" fill="white" text-anchor="middle" alignment-baseline="middle">{texto_central}</text>
            <text x="50" y="65" font-family="Arial" font-size="9" fill="#AAAAAA" text-anchor="middle" alignment-baseline="middle">VIDA ÚTIL</text>
        </svg>
        <p style="color: {color}; font-weight: bold; font-size: 14px; margin-top: 10px; margin-bottom: 0px;">{texto_estado}</p>
        <p style="color: #AAAAAA; font-size: 12px; margin-top: 2px; margin-bottom: 0;">{subtexto}</p>
    </div>
    """
    return svg_html
    
def render_radar(df, user):
    st.header("🏠 Radar de la Unidad (Escáner 360°)")
    if df.empty:
        st.info("No hay datos registrados en el historial para mostrar el radar.")
        return

    # 1. Selector de Bus
    if user['role'] in ['owner', 'mechanic']:
        buses_disponibles = sorted(df['bus'].unique())
        if not buses_disponibles:
            st.warning("No hay buses registrados aún.")
            return
        bus_sel = st.selectbox("🎯 Selecciona la Unidad a Escanear:", buses_disponibles)
    else:
        bus_sel = user['bus']
        st.subheader(f"🎯 Unidad Asignada: {bus_sel}")

    df_bus = df[df['bus'] == bus_sel]
    if df_bus.empty:
        st.warning(f"Sin historial de mantenimientos para el bus {bus_sel}.")
        return

    # 2. Kilometraje Real
    km_actual_real = df_bus['km_current'].max()
    
    st.markdown(f"""
        <div style='background-color:#1E1E1E; padding:15px; border-radius:10px; text-align:center; border: 1px solid #4CAF50;'>
            <h2 style='color:#4CAF50; margin:0;'>🚗 KILOMETRAJE ACTUAL: {km_actual_real:,.0f} km</h2>
        </div>
        <br>
    """, unsafe_allow_html=True)

    st.subheader("🛠️ Panel de Control de Sistemas")
    
    # 3. EXTRAER TODAS LAS CATEGORÍAS
    ultimos_registros = df_bus.sort_values('date', ascending=False).drop_duplicates(subset=['category'])
    
    alertas = []
    for _, r in ultimos_registros.iterrows():
        cat = r['category']
        meta = r.get('km_next', 0)
        
        if meta > 0:
            faltan = meta - km_actual_real
        else:
            faltan = float('inf') 
            
        alertas.append({"cat": cat, "faltan": faltan, "meta": meta})
        
    # Ordenamos: Vencidos -> Próximos -> Óptimos -> Grises
    alertas = sorted(alertas, key=lambda x: x['faltan'])
    
    # 4. Dibujamos los Relojes y sus BOTONES DE INFO
    c1, c2, c3 = st.columns(3)
    columnas = [c1, c2, c3]
    
    datos_para_ia = f"El bus {bus_sel} tiene un kilometraje actual de {km_actual_real:,.0f} km.\n"
    
    for i, al in enumerate(alertas):
        col = columnas[i % 3] 
        cat = al['cat']
        faltan = al['faltan']
        meta = al['meta']
        
        with col:
            # Dibujamos el reloj SVG
            reloj_svg = draw_svg_gauge(cat, faltan, meta)
            st.markdown(reloj_svg, unsafe_allow_html=True)
            
            # --- NUEVO: VENTANA EMERGENTE (POPOVER) DE INFORMACIÓN ---
            with st.popover(f"🔍 Ver info de {cat}", use_container_width=True):
                st.markdown(f"**Historial de {cat}**")
                
                # Buscamos los últimos 3 registros de esta pieza en este bus
                historial_cat = df_bus[df_bus['category'] == cat].sort_values('date', ascending=False).head(3)
                
                if not historial_cat.empty:
                    for _, req in historial_cat.iterrows():
                        f_str = req['date'].strftime('%d/%m/%Y')
                        
                        # Mostramos un mini-resumen súper claro
                        st.caption(f"📅 **{f_str}** | KM Guardado: {req['km_current']:,.0f}")
                        st.write(f"📝 {req.get('observations', 'Sin observaciones adicionales.')}")
                        
                        # Si gastó dinero, se lo mostramos
                        costo_total = req.get('mec_cost', 0) + req.get('com_cost', 0)
                        if costo_total > 0:
                            st.write(f"💵 **Costo Total:** ${costo_total}")
                            
                        # Si hay mecánico o comercio, lo detallamos
                        if req.get('mec_name') and req['mec_name'] != "N/A":
                            st.caption(f"👨‍🔧 Mecánico: {req['mec_name']}")
                        if req.get('com_name') and req['com_name'] != "N/A":
                            st.caption(f"🛒 Repuestos: {req['com_name']}")
                            
                        st.divider() # Línea separadora entre mantenimientos
                else:
                    st.info("No hay registros detallados para mostrar.")
            
            # Espaciado para que se vea limpio
            st.write("") 
            
            # Recopilamos info para la IA (Igual que antes)
            if meta <= 0:
                datos_para_ia += f"- {cat}: No tiene meta de cambio programada.\n"
            elif faltan < 0:
                datos_para_ia += f"- {cat}: VENCIDO por {abs(faltan):,.0f} km.\n"
            elif faltan <= 1500:
                datos_para_ia += f"- {cat}: Próximo, faltan {faltan:,.0f} km.\n"
            else:
                datos_para_ia += f"- {cat}: Óptimo, faltan {faltan:,.0f} km.\n"

    # 5. DIAGNÓSTICO IA
    st.divider()
    st.subheader("🧠 Asesor de Taller IA")
    if st.button("🔍 Generar Diagnóstico con IA", type="primary", use_container_width=True):
        if not HAS_AI: 
            st.error("⚠️ La Inteligencia Artificial no está configurada. Revisa tus Secrets en Streamlit.")
        else:
            with st.spinner("Analizando desgastes y cruzando datos del radar..."):
                try:
                    model = get_ai_model()
                    if model:
                        prompt = f"""
                        Eres el Jefe de Taller Automotriz experto. Analiza este radar 360 del bus:
                        {datos_para_ia}
                        
                        Redacta en 3 partes:
                        1. 🚨 **Urgente:** Qué debe detenerse o revisarse hoy mismo.
                        2. ⚠️ **Prevención:** A qué prestar atención esta semana.
                        3. 💡 **Consejo:** Un tip sobre los sistemas "sin meta programada" si los hay.
                        """
                        response = model.generate_content(prompt)
                        st.info(response.text)
                    else:
                        st.error("❌ No se pudo cargar el modelo de IA.")
                except Exception as e:
                    st.error("❌ Error de conexión con Google Gemini.")
                    
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
    """Muestra alertas y permite edición total al Administrador"""
    if not REFS: return
    
    notifs = REFS["data"].collection("notifications").where("fleetId", "==", user['fleet']).where("target_role", "==", user['role']).where("status", "==", "unread").stream()
    lista_notifs = [{"id": n.id, **n.to_dict()} for n in notifs]
    
    if lista_notifs:
        st.error(f"🔔 TIENES {len(lista_notifs)} NOTIFICACIÓN(ES) NUEVA(S) QUE REQUIEREN TU ATENCIÓN")
        
        for n in lista_notifs:
            with st.container(border=True):
                st.write(f"📩 **De:** {n.get('sender')} | 📅 {n.get('date', '')[:10]}")
                st.info(f"💬 **Mensaje:** {n.get('message', '')}")
                
                # --- EDICIÓN TOTAL DIRECTO DESDE LA ALERTA ---
                if 'log_id' in n and user['role'] == 'owner':
                    log_ref = REFS["data"].collection("logs").document(n['log_id'])
                    log_doc = log_ref.get()
                    
                    if log_doc.exists:
                        log_data = log_doc.to_dict()
                        with st.expander("✏️ Corregir TODO el registro aquí mismo"):
                            with st.form(f"quick_edit_{n['id']}"):
                                st.write(f"**Actualizando:** Bus {log_data.get('bus')}")
                                
                                # Datos a modificar
                                new_cat = st.text_input("Categoría", value=log_data.get('category', ''))
                                new_obs = st.text_area("Detalle", value=log_data.get('observations', ''))
                                
                                ck1, ck2 = st.columns(2)
                                new_ka = ck1.number_input("KM Actual", value=int(log_data.get('km_current', 0)), step=1)
                                new_kn = ck2.number_input("Próximo Cambio", value=int(log_data.get('km_next', 0)), step=1)
                                
                                cm1, cm2 = st.columns(2)
                                new_mn = cm1.text_input("Mecánico", value=log_data.get('mec_name', 'N/A'))
                                new_mc = cm1.number_input("Costo Mano Obra $", value=float(log_data.get('mec_cost', 0.0)))
                                new_rn = cm2.text_input("Comercio", value=log_data.get('com_name', 'N/A'))
                                new_rc = cm2.number_input("Costo Repuestos $", value=float(log_data.get('com_cost', 0.0)))
                                
                                if st.form_submit_button("💾 Aplicar Corrección y Cerrar Alerta", type="primary"):
                                    log_ref.update({
                                        "category": new_cat, "observations": new_obs,
                                        "km_current": new_ka, "km_next": new_kn,
                                        "mec_name": new_mn, "mec_cost": new_mc,
                                        "com_name": new_rn, "com_cost": new_rc
                                    })
                                    REFS["data"].collection("notifications").document(n['id']).update({"status": "read"})
                                    st.cache_data.clear()
                                    st.success("✅ Corregido!")
                                    time.sleep(1)
                                    st.rerun()
                    else:
                        st.warning("⚠️ El registro original ya fue eliminado.")

                if st.button("✅ Simplemente marcar como leído", key=f"read_{n['id']}"):
                    REFS["data"].collection("notifications").document(n['id']).update({"status": "read"})
                    st.rerun()
                    
        st.divider()

def render_communications(user):
    """Módulo completo con Historial de Mensajes y Alertas"""
    st.header("💬 Centro de Mensajes e Historial")
    
    # Creamos 3 pestañas: Redactar, Bandeja de Entrada y Enviados
    t1, t2, t3 = st.tabs(["📝 Redactar Alerta", "📥 Bandeja de Entrada", "📤 Enviados"])
    
    with t1:
        with st.form("send_message_form", clear_on_submit=True):
            st.subheader("📤 Redactar Nueva Alerta")
            
            roles = {"Administrador/Dueño": "owner", "Mecánicos": "mechanic", "Conductores": "driver"}
            destino = st.selectbox("Enviar a todos los:", list(roles.keys()))
            mensaje = st.text_area("Escribe tu mensaje o reporte:")
            
            # UN SOLO BOTÓN
            enviar_btn = st.form_submit_button("🔔 Guardar y Avisar por WhatsApp Automáticamente", type="primary", use_container_width=True)
            
        if enviar_btn:
            if mensaje.strip():
                # 1. Guardamos el mensaje en la base de datos
                REFS["data"].collection("notifications").add({
                    "fleetId": user['fleet'],
                    "sender": f"{user['name']} ({user['role'].upper()})",
                    "target_role": roles[destino],
                    "message": mensaje,
                    "date": datetime.now().isoformat(),
                    "status": "unread"
                })
                
                st.success("✅ ¡Mensaje guardado! Abriendo WhatsApp...")
                
                # 2. Preparamos el enlace de WhatsApp
                texto_wa = f"🚨 *AVISO DE ITERO AI*\nHola, te he dejado un nuevo mensaje en el sistema:\n\n_{mensaje}_\n\nIngresa a la app para revisarlo."
                
                if roles[destino] == "owner":
                    # --- AQUÍ ESTÁ LA MAGIA: LEER EL NÚMERO REAL DEL DUEÑO ---
                    fleet_doc = REFS["fleets"].document(user['fleet']).get()
                    numero_admin = fleet_doc.to_dict().get("boss_phone", APP_CONFIG['BOSS_PHONE']) if fleet_doc.exists else APP_CONFIG['BOSS_PHONE']
                    
                    link = f"https://wa.me/{format_phone(numero_admin)}?text={urllib.parse.quote(texto_wa)}"
                else:
                    link = f"https://wa.me/?text={urllib.parse.quote(texto_wa)}"
                
                # 3. TRUCO JAVASCRIPT: Forzar la apertura de WhatsApp automáticamente
                js_abrir_wa = f"""
                <script>
                    window.open('{link}', '_blank');
                </script>
                """
                # Inyectamos el código en la app sin que se vea
                st.components.v1.html(js_abrir_wa, height=0)
                
            else:
                st.error("❌ Por favor, escribe un mensaje.")
    with t2:
        st.subheader("📥 Historial de Mensajes Recibidos")
        # Consultamos TODOS los mensajes dirigidos a este rol en esta flota
        notifs_ref = REFS["data"].collection("notifications").where("fleetId", "==", user['fleet']).where("target_role", "==", user['role']).stream()
        recibidos = [{"id": n.id, **n.to_dict()} for n in notifs_ref]
        
        if recibidos:
            df_rec = pd.DataFrame(recibidos)
            # Ordenamos del más nuevo al más viejo
            df_rec['date_obj'] = pd.to_datetime(df_rec['date'])
            df_rec = df_rec.sort_values('date_obj', ascending=False)
            
            for _, r in df_rec.iterrows():
                fecha_formato = r['date_obj'].strftime('%d/%m/%Y %H:%M')
                es_nuevo = r.get('status') == 'unread'
                icono = "🆕 (NO LEÍDO)" if es_nuevo else "✅ (Leído)"
                
                with st.expander(f"{icono} | 📅 {fecha_formato} | De: {r.get('sender', 'Desconocido')}"):
                    st.write(f"**Mensaje:** {r.get('message', '')}")
                    
                    if r.get('log_id'):
                        st.caption(f"🔗 ID de Reporte vinculado: {r['log_id']}")
                        
                    if es_nuevo:
                        if st.button("Marcar como leído", key=f"hist_read_{r['id']}"):
                            REFS["data"].collection("notifications").document(r['id']).update({"status": "read"})
                            st.rerun()
        else:
            st.info("No tienes mensajes en tu bandeja de entrada.")

    with t3:
        st.subheader("📤 Historial de Mensajes Enviados")
        # Consultamos todos los mensajes enviados por el usuario actual
        sender_id = f"{user['name']} ({user['role'].upper()})"
        sent_ref = REFS["data"].collection("notifications").where("fleetId", "==", user['fleet']).where("sender", "==", sender_id).stream()
        enviados = [{"id": n.id, **n.to_dict()} for n in sent_ref]
        
        if enviados:
            df_env = pd.DataFrame(enviados)
            df_env['date_obj'] = pd.to_datetime(df_env['date'])
            df_env = df_env.sort_values('date_obj', ascending=False)
            
            for _, r in df_env.iterrows():
                fecha_formato = r['date_obj'].strftime('%d/%m/%Y %H:%M')
                estado_lectura = "Visto por destinatario 👀" if r.get('status') == 'read' else "Entregado, no leído 📩"
                
                with st.expander(f"📅 {fecha_formato} | Para: {r.get('target_role', '').upper()} | {estado_lectura}"):
                    st.write(f"**Tu Mensaje:** {r.get('message', '')}")
        else:
            st.info("Aún no has enviado ningún mensaje por el sistema.")
def render_reports(df, user):
    st.header("📊 Reportes y Auditoría")
    if df.empty: 
        st.warning("No hay datos.")
        return
        
    t1, t2, t3 = st.tabs(["📊 Gráficos Visuales", "🚦 Estado de Unidades", "📜 Historial Detallado"])
    
    with t1:
        st.subheader("📈 Análisis Financiero y Operativo")
        
        # 1. Calculamos los costos en el dataframe original
        df['total_cost'] = df.get('mec_cost', 0) + df.get('com_cost', 0)
        
        # 2. Creamos el filtro independiente para el Administrador
        buses_disp = sorted(df['bus'].unique())
        filtro_bus = st.selectbox("🎯 Filtrar gráficos por Unidad:", ["TODA LA FLOTA"] + list(buses_disp))
        
        # Filtramos los datos según lo que elijas
        df_graficos = df if filtro_bus == "TODA LA FLOTA" else df[df['bus'] == filtro_bus]
        
        if df_graficos.empty:
            st.info("No hay gastos registrados para esta selección.")
        else:
            # 3. Tarjetas KPI (Resumen Financiero Rápido)
            gasto_total = df_graficos['total_cost'].sum()
            gasto_rep = df_graficos['com_cost'].sum()
            gasto_mo = df_graficos['mec_cost'].sum()
            
            # Usamos CSS y SVG embebido para darle un toque premium a las métricas
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; gap:15px; margin-bottom: 20px;">
                <div style="flex:1; background-color:#1E1E1E; padding:20px; border-radius:10px; border-left: 5px solid #28a745; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <p style="color:#AAAAAA; font-size:14px; margin:0; text-transform:uppercase;">💰 Gasto Total</p>
                    <h2 style="color:white; margin:5px 0 0 0;">${gasto_total:,.2f}</h2>
                </div>
                <div style="flex:1; background-color:#1E1E1E; padding:20px; border-radius:10px; border-left: 5px solid #ffc107; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <p style="color:#AAAAAA; font-size:14px; margin:0; text-transform:uppercase;">🛒 Repuestos</p>
                    <h2 style="color:white; margin:5px 0 0 0;">${gasto_rep:,.2f}</h2>
                </div>
                <div style="flex:1; background-color:#1E1E1E; padding:20px; border-radius:10px; border-left: 5px solid #17a2b8; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <p style="color:#AAAAAA; font-size:14px; margin:0; text-transform:uppercase;">👨‍🔧 Mano de Obra</p>
                    <h2 style="color:white; margin:5px 0 0 0;">${gasto_mo:,.2f}</h2>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 4. Gráficos Interactivos Modernos
            col_g1, col_g2 = st.columns(2)
            
            # Gráfico 1: Donut Chart de Categorías
            fig_pie = px.pie(
                df_graficos, 
                values='total_cost', 
                names='category', 
                title=f'Distribución de Gastos ({filtro_bus})',
                hole=0.45, # Esto lo convierte en un "Donut"
                color_discrete_sequence=px.colors.qualitative.Bold # Colores más fuertes y vivos
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            fig_pie.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)") # Fondo transparente
            col_g1.plotly_chart(fig_pie, use_container_width=True)
            
            # Gráfico 2: Dinámico según la selección
            if filtro_bus == "TODA LA FLOTA":
                # Ranking de unidades (Con barras de calor rojas para los más gastadores)
                costos_por_bus = df_graficos.groupby('bus')['total_cost'].sum().reset_index()
                fig_bar = px.bar(
                    costos_por_bus, 
                    x='bus', 
                    y='total_cost', 
                    title='Costo Total por Unidad (Ranking)',
                    text_auto='.2s',
                    color='total_cost', 
                    color_continuous_scale='Reds' # 🔥 MAPA DE CALOR ROJO
                )
                fig_bar.update_layout(xaxis_title="Unidad (Bus)", yaxis_title="Costo ($)", coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                col_g2.plotly_chart(fig_bar, use_container_width=True)
            else:
                # Si el Administrador selecciona un solo bus, le mostramos la línea de tiempo de gastos
                df_graficos['fecha_corta'] = pd.to_datetime(df_graficos['date']).dt.date
                df_tiempo = df_graficos.groupby('fecha_corta')['total_cost'].sum().reset_index()
                fig_line = px.line(
                    df_tiempo, 
                    x='fecha_corta', 
                    y='total_cost', 
                    title=f'Línea de Tiempo de Gastos (Bus {filtro_bus})',
                    markers=True,
                    line_shape='spline' # Línea curva suave
                )
                fig_line.update_traces(line_color="#28a745", marker=dict(size=8, color="#ffffff", line=dict(width=2, color="#28a745")))
                fig_line.update_layout(xaxis_title="Fecha del Gasto", yaxis_title="Costo en USD", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                col_g2.plotly_chart(fig_line, use_container_width=True)

    with t2:
        st.subheader("🚦 Buscador y Estado de Unidades")
        
        buses_list = sorted(df['bus'].unique())
        
        if not buses_list:
            st.info("No hay unidades registradas aún.")
        else:
            # --- EL BUSCADOR ---
            bus_seleccionado = st.selectbox("🔍 Buscar por número de Unidad (Bus):", ["TODOS LOS BUSES"] + list(buses_list))
            
            # 1. KM máximo reportado para cada bus (El real actual)
            km_reales = df.groupby('bus')['km_current'].max()
            
            # 2. Última meta programada para cada pieza
            mantenimientos = df[df['km_next'] > 0].sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
            
            if bus_seleccionado != "TODOS LOS BUSES":
                # --- VISTA DETALLADA DE UN SOLO BUS ---
                mantenimientos_bus = mantenimientos[mantenimientos['bus'] == bus_seleccionado]
                km_actual_bus = km_reales.get(bus_seleccionado, 0)
                
                st.markdown(f"### 🚍 Unidad: {bus_seleccionado} | 🚗 KM Actual: **{km_actual_bus:,.0f}**")
                
                if mantenimientos_bus.empty:
                    st.info(f"El Bus {bus_seleccionado} no tiene mantenimientos programados a futuro.")
                else:
                    datos_bus = []
                    for _, r in mantenimientos_bus.iterrows():
                        cat = r['category']
                        km_meta = r['km_next']
                        faltan = km_meta - km_actual_bus
                        
                        if faltan < 0: estado = "🔴 VENCIDO"
                        elif faltan <= 1500: estado = "🟡 PRÓXIMO"
                        else: estado = "🟢 OK"
                            
                        datos_bus.append({
                            "Categoría": cat,
                            "Estado": estado,
                            "KM Faltantes": faltan,
                            "Meta Programada": km_meta,
                            "Último Reporte": r['date'].strftime('%d/%m/%Y')
                        })
                    
                    # Mostrar tabla ordenada desde lo más urgente (menor KM faltante) a lo más sano
                    df_bus = pd.DataFrame(datos_bus).sort_values('KM Faltantes')
                    
                    # Formatear números para que se vean bonitos en la tabla
                    df_bus['KM Faltantes'] = df_bus['KM Faltantes'].apply(lambda x: f"{x:,.0f} km")
                    df_bus['Meta Programada'] = df_bus['Meta Programada'].apply(lambda x: f"{x:,.0f} km")
                    
                    st.dataframe(df_bus, use_container_width=True, hide_index=True)
                    
            else:
                # --- VISTA PANORÁMICA (TODOS LOS BUSES) ---
                estado_flota = {}
                for bus in km_reales.index:
                    estado_flota[bus] = {"🚍 Unidad": bus, "🚗 KM Actual": f"{km_reales[bus]:,.0f}"}
                    
                for _, r in mantenimientos.iterrows():
                    bus = r['bus']
                    cat = r['category']
                    km_meta = r['km_next']
                    km_actual_real = km_reales.get(bus, r['km_current'])
                    faltan = km_meta - km_actual_real
                    
                    if faltan < 0: estado = "🔴 Vencido"
                    elif faltan <= 1500: estado = "🟡 Próximo"
                    else: estado = "🟢 OK"
                        
                    estado_flota[bus][cat] = f"{estado} ({faltan:,.0f} km)"
                    
                if estado_flota:
                    df_estado = pd.DataFrame(list(estado_flota.values())).fillna("⚪ -")
                    cols_base = ["🚍 Unidad", "🚗 KM Actual"]
                    cols_extras = sorted([c for c in df_estado.columns if c not in cols_base])
                    df_estado = df_estado[cols_base + cols_extras]
                    
                    st.dataframe(df_estado, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay metas programadas en toda la flota.")

    with t3:
        st.subheader("📜 Bitácora de Movimientos (EDICIÓN TOTAL)")
        df_sorted = df.sort_values('date', ascending=False)
        
        lista_mecs = ["N/A"] + sorted([str(m) for m in df.get('mec_name', pd.Series()).unique() if pd.notna(m) and m not in ["N/A", ""]])
        lista_coms = ["N/A"] + sorted([str(c) for c in df.get('com_name', pd.Series()).unique() if pd.notna(c) and c not in ["N/A", ""]])
        
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
                    
                    if user['role'] == 'owner':
                        edit_mode = st.checkbox(f"✏️ Editar este registro por completo", key=f"edit_check_{r['id']}")
                        if edit_mode:
                            with st.form(f"form_edit_{r['id']}"):
                                st.warning("Modifica cualquier campo del reporte y guarda.")
                                
                                cat_opciones = ["Aceite Motor", "Caja/Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Combustible", "Motor", "Otro"]
                                cat_actual = r.get('category', 'Otro')
                                if cat_actual not in cat_opciones: cat_opciones.append(cat_actual)
                                
                                new_cat = st.selectbox("Categoría", cat_opciones, index=cat_opciones.index(cat_actual))
                                new_obs = st.text_area("Detalle", value=r.get('observations', ''))
                                
                                c_k1, c_k2 = st.columns(2)
                                new_ka = c_k1.number_input("KM Actual", value=int(r['km_current']), step=1)
                                new_kn = c_k2.number_input("Próximo (KM Meta)", value=int(r.get('km_next', 0)), step=1)
                                
                                st.markdown("##### 💵 Proveedores y Costos")
                                c_m, c_c = st.columns(2)
                                
                                m_actual = str(r.get('mec_name', 'N/A'))
                                if m_actual not in lista_mecs: lista_mecs.append(m_actual)
                                c_actual = str(r.get('com_name', 'N/A'))
                                if c_actual not in lista_coms: lista_coms.append(c_actual)
                                
                                new_mn = c_m.selectbox("Mecánico", lista_mecs, index=lista_mecs.index(m_actual))
                                new_mc = c_m.number_input("Costo Mano Obra $", value=float(r.get('mec_cost', 0.0)))
                                
                                new_rn = c_c.selectbox("Comercio", lista_coms, index=lista_coms.index(c_actual))
                                new_rc = c_c.number_input("Costo Repuestos/Total $", value=float(r.get('com_cost', 0.0)))
                                
                                col_btn1, col_btn2 = st.columns(2)
                                if col_btn1.form_submit_button("💾 Guardar Todos los Cambios", type="primary"):
                                    REFS["data"].collection("logs").document(r['id']).update({
                                        "category": new_cat, "observations": new_obs,
                                        "km_current": new_ka, "km_next": new_kn,
                                        "mec_name": new_mn, "mec_cost": new_mc,
                                        "com_name": new_rn, "com_cost": new_rc
                                    })
                                    st.cache_data.clear()
                                    st.success("✅ Registro actualizado por completo.")
                                    time.sleep(1)
                                    st.rerun()
                                    
                        if st.button("🗑️ Eliminar Reporte", key=f"del_rep_{r['id']}"):
                            REFS["data"].collection("logs").document(r['id']).delete()
                            st.cache_data.clear()
                            st.rerun()
                            
                    elif user['role'] in ['driver', 'mechanic']:
                        st.info("💡 ¿Hay algún error en este registro?")
                        explicacion = st.text_area("Explica qué está mal y cuál es el dato correcto:", key=f"exp_{r['id']}")
                        col_wa, col_app = st.columns(2)
                        
                        if col_app.button("🔔 Enviar Solicitud por App", key=f"req_edit_{r['id']}", use_container_width=True):
                            if explicacion.strip() == "":
                                st.error("❌ Escribe tu explicación antes de enviar.")
                            else:
                                from datetime import datetime
                                REFS["data"].collection("notifications").add({
                                    "fleetId": user['fleet'], "sender": f"{user['name']} ({user['role'].upper()})",
                                    "target_role": "owner", "log_id": r['id'],
                                    "message": f"🚩 CORRECCIÓN Bus {r['bus']} ({r['category']}): {explicacion}",
                                    "date": datetime.now().isoformat(), "status": "unread"
                                })
                                st.success("✅ Explicación enviada.")
                        
                        wa_text = f"Hola Administrador, necesito corregir el reporte del *Bus {r['bus']}*. Ya te envié los detalles por la campana de la App."
                        wa_link = f"https://wa.me/{format_phone(APP_CONFIG['BOSS_PHONE'])}?text={urllib.parse.quote(wa_text)}"
                        svg_whatsapp = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" width="16" height="16" fill="white" style="vertical-align: middle; margin-right: 8px;"><path d="M380.9 97.1C339 55.1 283.2 32 223.9 32c-122.4 0-222 99.6-222 222 0 39.1 10.2 77.3 29.6 111L0 480l117.7-30.9c32.4 17.7 68.9 27 106.1 27h.1c122.3 0 224.1-99.6 224.1-222 0-59.3-25.2-115-67.1-157.1zm-157 341.6c-33.2 0-65.7-8.9-94-25.7l-6.7-4-69.8 18.3L72 359.2l-4.4-7c-18.5-29.4-28.2-63.3-28.2-98.2 0-101.7 82.8-184.5 184.6-184.5 49.3 0 95.6 19.2 130.4 54.1 34.8 34.9 56.2 81.2 56.1 130.5 0 101.8-84.9 184.6-186.6 184.6zm101.2-138.2c-5.5-2.8-32.8-16.2-37.9-18-5.1-1.9-8.8-2.8-12.5 2.8-3.7 5.6-14.3 18-17.6 21.8-3.2 3.7-6.5 4.2-12 1.4-32.6-16.3-54-29.1-75.5-66-5.7-9.8 5.7-9.1 16.3-30.3 1.8-3.7.9-6.9-.5-9.7-1.4-2.8-12.5-30.1-17.1-41.2-4.5-10.8-9.1-9.3-12.5-9.5-3.2-.2-6.9-.2-10.6-.2-3.7 0-9.7 1.4-14.8 6.9-5.1 5.6-19.4 19-19.4 46.3 0 27.3 19.9 53.7 22.6 57.4 2.8 3.7 39.1 59.7 94.8 83.8 35.2 15.2 49 16.5 66.6 13.9 10.7-1.6 32.8-13.4 37.4-26.4 4.6-13 4.6-24.1 3.2-26.4-1.3-2.5-5-3.9-10.5-6.6z"/></svg>"""

                        col_wa.markdown(f'<a href="{wa_link}" target="_blank" class="btn-whatsapp" style="padding:10px; font-size:14px; text-align:center; display:flex; justify-content:center; align-items:center;">{svg_whatsapp} Avisar por WhatsApp</a>', unsafe_allow_html=True)
                
                with col_img:
                    if "photo_b64" in r and pd.notna(r["photo_b64"]) and r["photo_b64"]:
                        try:
                            st.image(f"data:image/jpeg;base64,{r['photo_b64']}", use_container_width=True)
                        except:
                            st.error("Error de imagen")
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
        # --- AQUÍ EMPIEZA LA MAGIA DE LAS CATEGORÍAS LIBRES ---
        cat_sel = c1.selectbox("Categoría", ["Aceite Motor", "Caja", "Corona", "Frenos", "Llantas", "Suspensión", "Eléctrico", "Otro (Escribir abajo)"])
        cat_otro = c1.text_input("Si elegiste 'Otro', especifica aquí (Ej: Refrigerante):")
        
        obs = st.text_area("Detalle")
        
        ka = c1.number_input("KM Actual", min_value=0, step=1)
        kn = c2.number_input("Próximo (KM Meta)", min_value=0, step=1)
        
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
                final_kn = kn if tp == "Preventivo" else 0
                
                # Definimos el nombre final de la categoría limpiando espacios y poniendo Mayúsculas iniciales
                if cat_sel == "Otro (Escribir abajo)" and cat_otro.strip() != "":
                    cat_final = cat_otro.strip().title()
                else:
                    cat_final = cat_sel.replace(" (Escribir abajo)", "")
                
                base64_photo = ""
                if foto_archivo:
                    base64_photo = base64.b64encode(foto_archivo.getvalue()).decode()
                
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": user['bus'],
                    "date": fecha_registro,
                    "category": cat_final, # <-- Guardamos la nueva categoría dinámica
                    "observations": obs,
                    "km_current": ka,
                    "km_next": final_kn,
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
    
    bus_df = df[df['bus'] == bus_id] if not df.empty and 'bus' in df.columns else pd.DataFrame()
    last_km = int(bus_df['km_current'].max()) if not bus_df.empty and 'km_current' in bus_df.columns else 0
    
    st.info(f"Registrando trabajo para la Unidad: **{bus_id}** | Último KM registrado: **{last_km:,.0f}**")
    
    coms = [p['name'] for p in providers if p['type'] == "Comercio"]
    
    with st.form("mechanic_log"):
        # --- NUEVA LÓGICA DE CATEGORÍA ---
        cat_sel = st.selectbox("Categoría del Daño", ["Mecánica", "Eléctrica", "Frenos", "Suspensión", "Motor", "Llantas", "Otro (Escribir abajo)"])
        cat_otro = st.text_input("Si elegiste 'Otro', especifica la pieza o sistema (Ej: Válvulas):")
        
        obs = st.text_area("Informe Técnico", placeholder="Describa el daño encontrado y la solución...")
        
        st.divider()
        st.write("⏱️ **Control de Kilometraje y Alertas**")
        c_km1, c_km2 = st.columns(2)
        
        km_actual = c_km1.number_input("Kilometraje Actual del Bus", min_value=0, value=last_km, step=100)
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
                # Definimos el nombre final de la categoría
                if cat_sel == "Otro (Escribir abajo)" and cat_otro.strip() != "":
                    cat_final = cat_otro.strip().title()
                else:
                    cat_final = cat_sel.replace(" (Escribir abajo)", "")
                
                bytes_data = foto.getvalue()
                b64 = base64.b64encode(bytes_data).decode()
                
                REFS["data"].collection("logs").add({
                    "fleetId": user['fleet'],
                    "bus": bus_id,
                    "date": datetime.now().isoformat(),
                    "category": cat_final, # <-- Guardamos la nueva categoría dinámica
                    "observations": f"REPORTE MECÁNICO ({user['name']}): {obs}",
                    "km_current": km_actual, 
                    "km_next": km_proximo,    
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
                
def render_ai_chat(df, user):
    html_header = """
<div style="display:flex; align-items:center; gap:18px; margin-bottom: 5px; padding-bottom: 15px; border-bottom: 1px solid #333333;">
<svg width="50" height="50" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="itero-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#00C6FF" />
<stop offset="100%" stop-color="#0072FF" />
</linearGradient>
<linearGradient id="sparkle-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#A0FEFE" />
<stop offset="100%" stop-color="#C3cfe2" />
</linearGradient>
</defs>
<path d="M50 10 A40 40 0 1 1 49.9 10 Z" fill="none" stroke="url(#itero-gradient)" stroke-width="2" stroke-dasharray="6 6" opacity="0.3"/>
<path d="M42 35 V65 M50 25 V75 M58 35 V65" stroke="url(#itero-gradient)" stroke-width="6" stroke-linecap="round" fill="none"/>
<path d="M70 50 A20 20 0 1 1 50 30 A20 20 0 0 1 65 35" stroke="url(#itero-gradient)" stroke-width="4" stroke-linecap="round" fill="none"/>
<path d="M62 38 L65 35 L62 32" stroke="url(#itero-gradient)" stroke-width="4" stroke-linecap="round" fill="none"/>
<path d="M50 42 C50 42 52 48 58 50 C52 52 50 58 50 58 C50 58 48 52 42 50 C48 48 50 42 50 42Z" fill="url(#sparkle-gradient)"/>
</svg>
<div>
<h1 style="margin:0; font-size: 38px; background: -webkit-linear-gradient(45deg, #00C6FF, #0072FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; letter-spacing: -1px;">IA Itero</h1>
<p style="color:#28a745; font-size: 12px; margin:0; font-weight:bold; text-transform:uppercase; letter-spacing:1px;">Asistente de Flota Inteligente</p>
</div>
</div>
<p style="color:#AAAAAA; font-size: 15px; margin-bottom: 25px; margin-top: 15px;">Bienvenido al centro de inteligencia de tu flota. Pregúntame sobre mantenimientos, gastos o predicciones de tus unidades.</p>
"""
    st.markdown(html_header, unsafe_allow_html=True)

    if not HAS_AI:
        st.error("⚠️ La Inteligencia Artificial no está configurada. Revisa tus Secrets en Streamlit.")
        return

    # --- 2. HISTORIAL DE CHAT ---
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Mostrar los mensajes anteriores (Usando avatares personalizados)
    for message in st.session_state.chat_history:
        avatar_icono = "🧑‍💻" if message["role"] == "user" else "✨"
        with st.chat_message(message["role"], avatar=avatar_icono):
            st.markdown(message["content"])

    # --- 3. CAJA DE TEXTO DEL USUARIO ---
    if prompt := st.chat_input("Ej: ¿Cuánto falta para la calibración de válvulas del Bus 05?"):
        
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        # --- 4. PROCESAMIENTO CON GEMINI (PERO COMO IA ITERO) ---
        with st.spinner("IA Itero está analizando tus datos..."):
            try:
                model = get_ai_model()
                
                # A. Traer las reglas del dueño
                fleet_doc = REFS["fleets"].document(user['fleet']).get()
                ai_rules = fleet_doc.to_dict().get("ai_rules", "") if fleet_doc.exists else ""
                
                # B. Construir un resumen exacto del estado de los buses
                contexto_datos = "ESTADO ACTUAL DE LOS MANTENIMIENTOS DE LA FLOTA:\n"
                if not df.empty:
                    df['total_cost'] = df.get('mec_cost', 0) + df.get('com_cost', 0)
                    km_reales = df.groupby('bus')['km_current'].max().to_dict()
                    ultimos_mantenimientos = df.sort_values('date', ascending=False).drop_duplicates(subset=['bus', 'category'])
                    
                    for _, r in ultimos_mantenimientos.iterrows():
                        b = r['bus']
                        c = r['category']
                        km_act = km_reales.get(b, 0)
                        km_meta = r.get('km_next', 0)
                        if km_meta > 0:
                            faltan = km_meta - km_act
                            estado = f"Faltan {faltan:,.0f} km" if faltan >= 0 else f"VENCIDO por {abs(faltan):,.0f} km"
                        else:
                            estado = "Sin meta programada a futuro."
                            
                        contexto_datos += f"- Bus {b} | {c}: KM Actual ({km_act:,.0f}). Meta Programada ({km_meta:,.0f}). Estado: {estado}.\n"
                        
                    logs_recientes = df[['date', 'bus', 'category', 'total_cost', 'observations']].head(20).to_string()
                else:
                    logs_recientes = "No hay registros."

                # C. Enviar todo al cerebro de la IA (Gemini) con nueva identidad
                sys_prompt = f"""
                Eres "IA Itero", el Asistente Inteligente oficial de la flota ITERO TITANIUM.
                Tu identidad es la de un experto en gestión automotriz, análisis de datos y predicción de mantenimientos.
                
                El usuario '{user['name']}' (Rol: {user['role']}) te hace una pregunta.
                
                REGLAS Y MANUAL ESPECÍFICO DE ESTA EMPRESA:
                {ai_rules}
                
                {contexto_datos}
                
                ÚLTIMOS TRABAJOS REGISTRADOS EN LA BITÁCORA:
                {logs_recientes}
                
                Pregunta del usuario: {prompt}
                
                INSTRUCCIONES DE RESPUESTA:
                1. Responde de forma natural, amistosa y muy profesional.
                2. Usa negritas (**) para resaltar números clave, costos y nombres de piezas.
                3. Usa listas si tienes que dar varias recomendaciones o pasos.
                4. Haz cálculos exactos basados en los datos que te pasé.
                5. Al final de respuestas complejas, puedes usar una frase como "Enviado por IA Itero".
                """
                
                response = model.generate_content(sys_prompt)
                
                # Mostrar respuesta de IA Itero
                with st.chat_message("assistant", avatar="✨"):
                    st.markdown(response.text)
                st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                
            except Exception as e:
                st.error(f"Hubo un error al conectar con el cerebro de IA Itero: {e}")
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
                "🤖 Chat IA": lambda: render_ai_chat(df, u), # <--- AGREGADO
                "💰 Pagos y Abonos": lambda: render_accounting(df, u, phone_map),
                "📊 Reportes": lambda: render_reports(df, u), 
                "🛠️ Reportar Taller": lambda: render_workshop(u, provs),
                "💬 Mensajes": lambda: render_communications(u),
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
                "🤖 Chat IA": lambda: render_ai_chat(df, u), # <--- AGREGADO
                "📝 Registrar Trabajo": lambda: render_mechanic_work(u, df, provs),
                "📊 Historial Técnico": lambda: render_reports(df, u), 
                "💬 Mensajes": lambda: render_communications(u),
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
                "🏠 Radar / Escáner": lambda: render_radar(df, u),
                "🤖 Chat Asistente IA": lambda: render_ai_chat(df, u), # <--- AGREGADO
                "📊 Reportes": lambda: render_reports(df, u), 
                "🛠️ Taller": lambda: render_workshop(u, provs),
                "💰 Contabilidad": lambda: render_accounting(df, u, phone_map),
                "💬 Mensajes": lambda: render_communications(u), 
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
