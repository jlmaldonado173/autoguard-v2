import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import time
import base64
from io import BytesIO
from PIL import Image
import json
import requests

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AutoGuard AI Elite V7 Pro", layout="wide", page_icon="🧠")

# --- ESTILOS PREMIUM ---
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .card { background: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 15px; }
    .ai-card { background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); border: 2px solid #3b82f6; padding: 20px; border-radius: 25px; }
    .profile-img { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid #2563eb; }
    .badge { padding: 4px 10px; border-radius: 8px; font-size: 0.75rem; font-weight: bold; }
    .badge-urgent { background: #fee2e2; color: #991b1b; border: 1px solid #f87171; animation: pulse 2s infinite; }
    .badge-ok { background: #dcfce7; color: #166534; border: 1px solid #4ade80; }
    .alert-banner { background: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 10px; color: #991b1b; margin-bottom: 20px; font-weight: bold; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZACIÓN DE FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON" in st.secrets:
                cred_info = json.loads(st.secrets["FIREBASE_JSON"])
                cred = credentials.Certificate(cred_info)
            else:
                cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error de base de datos: {e}")
            return None
    return firestore.client()

db = init_firebase()
app_id = "autoguard_enterprise_v7_pro"

# --- MOTOR DE INTELIGENCIA ARTIFICIAL (GEMINI) ---
def analizar_con_ia(logs_texto, bus_id):
    api_key = "" # El entorno proporciona la clave automáticamente
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    
    prompt = f"""
    Actúa como un Ingeniero Mecánico experto en flotas de buses. 
    Analiza el siguiente historial de mantenimiento de la Unidad {bus_id}:
    {logs_texto}
    Responde en formato profesional:
    1. Calificación de Cuidado (0-100%).
    2. Hábitos del conductor.
    3. Alertas críticas y Recomendación de ahorro.
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
    except: pass
    return "IA temporalmente fuera de línea."

# --- UTILIDADES ---
def process_image(image_file, size=(400, 400)):
    if image_file is None: return None
    try:
        img = Image.open(image_file)
        img.thumbnail(size)
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=60)
        return base64.b64encode(buffered.getvalue()).decode()
    except: return None

def get_fleet_ref(fleet_id):
    return db.collection("artifacts").document(app_id).collection("public").document("data").collection("fleets").document(fleet_id)

def get_user_ref(username):
    return db.collection("artifacts").document(app_id).collection("users").document(username)

# --- SESIÓN ---
if 'session' not in st.session_state: st.session_state.session = None

# --- LOGIN ---
if st.session_state.session is None:
    st.markdown("<h1 style='text-align:center;'>🚌 AutoGuard Elite Pro V7</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["👨‍✈️ Conductores", "📊 Propietarios"])
    
    with t1:
        with st.form("login_driver"):
            f_id = st.text_input("Código de Flota")
            u_name = st.text_input("Nombre de Usuario")
            u_bus = st.text_input("N° de Bus")
            if st.form_submit_button("INGRESAR"):
                if f_id:
                    st.session_state.session = {'role':'driver', 'fleet_id':f_id.upper().strip(), 'username':u_name, 'bus':u_bus}
                    st.rerun()
    with t2:
        with st.form("login_owner"):
            f_new = st.text_input("Código de Flota")
            o_name = st.text_input("Tu Nombre")
            if st.form_submit_button("GESTIONAR"):
                if f_new:
                    get_fleet_ref(f_new.upper().strip()).set({"owner": o_name}, merge=True)
                    st.session_state.session = {'role':'owner', 'fleet_id':f_new.upper().strip(), 'username':o_name, 'bus':'ADMIN'}
                    st.rerun()
else:
    sess = st.session_state.session
    fleet_ref = get_fleet_ref(sess['fleet_id'])
    
    with st.sidebar:
        st.title(f"{sess['username']}")
        st.write(f"📍 Flota: **{sess['fleet_id']}**")
        menu = st.radio("Menú", ["🏠 Dashboard", "🧠 IA Auditor", "🛠️ Reportar", "📂 SOAT/Documentos", "📦 Inventario", "👤 Perfil", "📋 Historial"])
        if st.button("🚪 Salir"):
            st.session_state.session = None
            st.rerun()

    # --- DASHBOARD CON ALERTAS CRÍTICAS ---
    if menu == "🏠 Dashboard":
        st.header("Resumen Operativo y Alertas")
        
        # Cargar datos
        logs_stream = fleet_ref.collection("logs").order_by("date", direction=firestore.Query.DESCENDING).limit(100).stream()
        logs = [{"id": l.id, **l.to_dict()} for l in logs_stream]
        vehs_stream = fleet_ref.collection("vehicles").stream()
        vehicles = {v.id: v.to_dict() for v in vehs_stream}

        # --- SECCIÓN DE ALERTAS CRÍTICAS (NUEVO) ---
        alertas_mantenimiento = []
        for v_id, v_data in vehicles.items():
            if v_data.get('next_service', 0) > 0:
                km_restantes = v_data['next_service'] - v_data.get('last_km', 0)
                if km_restantes <= 0:
                    alertas_mantenimiento.append(f"🚨 UNIDAD {v_id}: PASADA del servicio por {abs(km_restantes)} KM")
                elif km_restantes < 500:
                    alertas_mantenimiento.append(f"⚠️ UNIDAD {v_id}: Servicio urgente en {km_restantes} KM")

        if alertas_mantenimiento:
            for alerta in alertas_mantenimiento:
                st.markdown(f"<div class='alert-banner'>{alerta}</div>", unsafe_allow_html=True)

        if logs:
            df = pd.DataFrame(logs)
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Inversión Total", f"${df['cost'].sum():,.2f}")
            with c2: st.metric("Deuda Pendiente", f"${df[df['paid']==False]['cost'].sum():,.2f}")
            with c3: st.metric("Unidades Activas", len(vehicles))
            
            st.write("### Gasto por Categoría")
            st.bar_chart(df.groupby('category')['cost'].sum())
        else: st.info("No hay registros en esta flota.")

    # --- RESTO DE MÓDULOS (IA, REPORTAR, DOCS, ETC) ---
    elif menu == "🧠 IA Auditor":
        st.header("Auditoría con IA")
        logs_stream = fleet_ref.collection("logs").stream()
        logs_list = [l.to_dict() for l in logs_stream]
        if logs_list:
            bus_list = sorted(list(set([l['bus'] for l in logs_list])))
            bus_sel = st.selectbox("Bus a analizar", bus_list)
            if st.button("🔍 Iniciar Auditoría IA"):
                with st.spinner("IA Analizando..."):
                    bus_logs = [f"- {l['desc']} (${l['cost']})" for l in logs_list if l['bus'] == bus_sel]
                    st.markdown(f'<div class="ai-card">{analizar_con_ia(chr(10).join(bus_logs), bus_sel)}</div>', unsafe_allow_html=True)

    elif menu == "🛠️ Reportar":
        st.header(f"Reporte Unidad {sess['bus']}")
        with st.form("rep_form"):
            col1, col2 = st.columns(2)
            with col1:
                cat = st.selectbox("Categoría", ["Motor", "Frenos", "Caja", "Chasis", "Luces", "Llantas", "Otro"])
                desc = st.text_input("Trabajo realizado")
                cost = st.number_input("Costo ($)", min_value=0.0)
            with col2:
                mech = st.text_input("Mecánico")
                km = st.number_input("Kilometraje Actual", min_value=0)
                next_km = st.number_input("Siguiente Servicio (KM)", value=km+5000)
            foto = st.camera_input("Evidencia")
            if st.form_submit_button("GUARDAR"):
                img = process_image(foto)
                fleet_ref.collection("logs").add({
                    'bus': sess['bus'], 'category': cat, 'desc': desc, 'km': km, 'cost': cost,
                    'next_km': next_km, 'mechanic': mech, 'image': img, 'username': sess['username'],
                    'date': datetime.now(), 'paid': False
                })
                fleet_ref.collection("vehicles").document(sess['bus']).set({
                    'last_km': km, 'next_service': next_km, 'last_update': datetime.now()
                }, merge=True)
                st.success("Reporte Guardado")
                st.rerun()

    elif menu == "📂 SOAT/Documentos":
        st.header("Control de Vencimientos")
        with st.expander("➕ Registrar Documento"):
            with st.form("doc_f"):
                b_doc = st.text_input("N° Bus")
                t_doc = st.selectbox("Documento", ["SOAT", "Matrícula", "Revisión Técnica", "Seguro"])
                f_doc = st.date_input("Vencimiento")
                if st.form_submit_button("Guardar"):
                    fleet_ref.collection("documents").add({"bus": b_doc, "type": t_doc, "expiry": datetime.combine(f_doc, datetime.min.time())})
                    st.rerun()
        
        docs = fleet_ref.collection("documents").stream()
        for d in docs:
            item = d.to_dict()
            exp = item['expiry'].replace(tzinfo=None)
            rest = (exp - datetime.now()).days
            st.markdown(f"<div class='card'><b>Bus {item['bus']}</b> - {item['type']}<br>Vence en: <span class='badge {'badge-urgent' if rest < 10 else 'badge-ok'}'>{rest} días</span></div>", unsafe_allow_html=True)

    elif menu == "📦 Inventario":
        st.header("Bodega")
        c1, c2 = st.columns(2)
        with c1:
            with st.form("inv_f"):
                p_inv = st.text_input("Repuesto")
                q_inv = st.number_input("Cantidad", min_value=0)
                if st.form_submit_button("Actualizar Stock"):
                    fleet_ref.collection("inventory").document(p_inv).set({"qty": q_inv}, merge=True)
                    st.rerun()
        with c2:
            items = fleet_ref.collection("inventory").stream()
            for i in items: st.write(f"📦 {i.id}: **{i.to_dict()['qty']} uds**")

    elif menu == "📋 Historial":
        st.header("Historial de Flota")
        logs_stream = fleet_ref.collection("logs").order_by("date", direction=firestore.Query.DESCENDING).stream()
        for l in logs_stream:
            item = l.to_dict()
            with st.expander(f"Bus {item['bus']} | {item['date'].strftime('%d/%m')} | ${item['cost']}"):
                st.write(f"**Trabajo:** {item['desc']} ({item['category']})")
                if item.get('image'): st.image(base64.b64decode(item['image']), width=300)
                if sess['role'] == 'owner' and not item.get('paid'):
                    if st.button("Marcar Pagado", key=l.id):
                        fleet_ref.collection("logs").document(l.id).update({"paid": True}); st.rerun()

st.caption(f"AutoGuard Elite Enterprise V7.1 - Alertas Activas | ID: {app_id}")