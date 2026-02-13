import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# Intentar cargar Plotly para gráficos contables
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- 1. CONFIGURACIÓN DEL SISTEMA ---
st.set_page_config(page_title="Itaro v37 - Tridente", layout="wide", page_icon="🚛")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Error de Base de Datos: {e}")
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
FLEETS_REF = db.collection("artifacts").document(APP_ID).collection("registered_fleets")
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. GESTIÓN DE SESIÓN Y SEGURIDAD ---
if 'user' not in st.session_state:
    params = st.query_params
    if "f" in params:
        st.session_state.user = {'role': params.get("r"), 'fleet': params.get("f"), 'name': params.get("u"), 'bus': params.get("b")}
        st.rerun()

# --- 3. PANTALLA DE ACCESO (LOGIN / REGISTRO) ---
if 'user' not in st.session_state:
    st.title("🛡️ Itaro | Gestión Profesional")
    t1, t2 = st.tabs(["Ingresar", "Registrar Flota"])
    
    with t1:
        f_id = st.text_input("Código de Flota").upper().strip()
        u_name = st.text_input("Usuario").upper().strip()
        u_bus = st.text_input("Unidad")
        u_role = st.selectbox("Rol", ["Conductor", "Administrador/Dueño"])
        if st.button("INGRESAR"):
            if FLEETS_REF.document(f_id).get().exists:
                # Verificación simple para demo (en prod usar auth completa)
                u_data = {'role':'owner' if "Adm" in u_role else 'driver', 'fleet':f_id, 'name':u_name, 'bus':u_bus}
                st.session_state.user = u_data
                st.query_params.update({"f":f_id, "u":u_name, "b":u_bus, "r":u_data['role']})
                st.rerun()
            else: st.error("Flota no encontrada.")

    with t2:
        new_f = st.text_input("Nuevo ID").upper().strip()
        if st.button("CREAR"):
            if new_f and not FLEETS_REF.document(new_f).get().exists:
                FLEETS_REF.document(new_f).set({"created": datetime.now(), "status": "active"})
                st.success("Creada.")

else:
    u = st.session_state.user

    # --- 4. MOTOR DE DATOS (MANTENIMIENTO + CONTABILIDAD) ---
    def load_data():
        # Proveedores (Comunicación)
        p_docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
        provs = [p.to_dict() | {"id": p.id} for p in p_docs]
        phones = {p['name']: p['phone'] for p in provs}
        
        # Logs (Mantenimiento y Contabilidad)
        q = DATA_REF.collection("logs").where("fleetId", "==", u['fleet'])
        if u['role'] == 'driver': q = q.where("bus", "==", u['bus'])
        logs = [l.to_dict() | {"id": l.id} for l in q.stream()]
        
        cols = ['bus', 'category', 'km_current', 'km_next', 'date', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid', 'mec_name', 'com_name']
        if not logs: return provs, phones, pd.DataFrame(columns=cols)
        
        df = pd.DataFrame(logs)
        for c in cols: 
            if c not in df.columns: df[c] = 0
            
        # Limpieza numérica
        for c in ['km_current', 'km_next', 'mec_cost', 'com_cost', 'mec_paid', 'com_paid']:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return provs, phones, df

    providers, phone_book, df = load_data()

    # --- INTERFAZ PRINCIPAL ---
    st.sidebar.markdown(f"### 🚛 {u['fleet']}\nUsuario: **{u['name']}**")
    menu = ["🏠 Inicio", "🛠️ Mantenimiento", "💰 Contabilidad", "📱 Comunicación/Directorio"]
    choice = st.sidebar.radio("Módulos", menu)

    # --- MÓDULO 1: MANTENIMIENTO (Vectalia Style) ---
    if choice == "🏠 Inicio":
        st.subheader(f"Estado de la Unidad {u['bus']}")
        if not df.empty:
            latest = df[df['bus'] == u['bus']].sort_values('date', ascending=False)
            if not latest.empty:
                row = latest.iloc[0]
                # Semáforo de Mantenimiento
                km_restante = row['km_next'] - row['km_current']
                color_km = "normal"
                if km_restante < 500: color_km = "inverse" # Rojo/Alerta
                
                c1, c2, c3 = st.columns(3)
                c1.metric("KM Actual", f"{row['km_current']:,.0f}")
                c2.metric("Próximo Servicio", f"{km_r:,.0f} KM", delta=km_restante, delta_color=color_km)
                
                days = (datetime.now() - row['date']).days
                c3.metric("Días sin reporte", f"{days} días")
                if days > 3: st.warning("⚠️ Actualiza tu kilometraje hoy.")

    elif choice == "🛠️ Mantenimiento":
        st.subheader("🔧 Registro de Taller")
        # Listas dinámicas desde el módulo de Comunicación
        mecs = [p['name'] for p in providers if p['type'] == "Mecánico"]
        coms = [p['name'] for p in providers if p['type'] == "Comercio"]
        
        with st.form("main_form"):
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Categoría", ["Motor", "Caja", "Aceite", "Frenos", "Llantas", "Eléctrico", "Otros"])
            km_a = col2.number_input("KM Actual", min_value=0)
            km_p = col2.number_input("Próximo Cambio (KM)", min_value=km_a)
            
            st.divider()
            c_m, c_c = st.columns(2)
            # Selección de proveedores (Vinculado a Comunicación)
            m_sel = c_m.selectbox("Mecánico", ["N/A"] + mecs)
            m_cost = c_m.number_input("Costo Mano de Obra ($)", min_value=0.0)
            
            c_sel = c_c.selectbox("Comercio Repuestos", ["N/A"] + coms)
            c_cost = c_c.number_input("Costo Repuestos ($)", min_value=0.0)
            
            if st.form_submit_button("GUARDAR EVENTO"):
                DATA_REF.collection("logs").add({
                    "fleetId": u['fleet'], "bus": u['bus'], "date": datetime.now().isoformat(),
                    "category": cat, "km_current": km_a, "km_next": km_p,
                    "mec_name": m_sel, "mec_cost": m_cost, "mec_paid": 0,
                    "com_name": c_sel, "com_cost": c_cost, "com_paid": 0
                })
                st.success("Evento registrado."); time.sleep(1); st.rerun()

    # --- MÓDULO 2: CONTABILIDAD (Control Financiero) ---
    elif choice == "💰 Contabilidad":
        st.header("📊 Finanzas de Flota")
        df['deuda_m'] = df['mec_cost'] - df['mec_paid']
        df['deuda_c'] = df['com_cost'] - df['com_paid']
        df['total'] = df['deuda_m'] + df['deuda_c']
        
        # Gráfico para el jefe
        if u['role'] == 'owner' and PLOTLY_AVAILABLE and not df.empty:
            fig = px.bar(df.groupby('bus')['total'].sum().reset_index(), x='bus', y='total', title="Deuda Total por Bus")
            st.plotly_chart(fig)

        # Tabla de deudas con acción de pago
        for _, r in df[df['total'] > 0].iterrows():
            with st.container(border=True):
                st.write(f"**Bus {r['bus']} - {r['category']}** ({r['date'].date()})")
                c1, c2, c3 = st.columns([2, 2, 1])
                if r['deuda_m'] > 0: c1.error(f"🔧 Mecánico: ${r['deuda_m']:,.0f}")
                if r['deuda_c'] > 0: c2.warning(f"📦 Repuestos: ${r['deuda_c']:,.0f}")
                
                if u['role'] == 'owner':
                    with c3.expander("Pagar"):
                        target = st.radio("Destino", ["Mecánico", "Comercio"], key=f"t_{r['id']}")
                        monto = st.number_input("Abono", key=f"v_{r['id']}")
                        if st.button("Confirmar", key=f"b_{r['id']}"):
                            field = "mec_paid" if target == "Mecánico" else "com_paid"
                            DATA_REF.collection("logs").document(r['id']).update({field: firestore.Increment(monto)})
                            
                            # Integración con Comunicación (WhatsApp)
                            p_name = r['mec_name'] if target == "Mecánico" else r['com_name']
                            tel = phone_book.get(p_name, "")
                            msg = f"Hola {p_name}, abono registrado de ${monto} por {r['category']} (Unidad {r['bus']})."
                            link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                            st.markdown(f"[📲 Enviar Comprobante]({link})")
                            time.sleep(2); st.rerun()

    # --- MÓDULO 3: COMUNICACIÓN (Directorio) ---
    elif choice == "📱 Comunicación/Directorio":
        st.header("Directorio y Contactos")
        
        with st.expander("➕ Nuevo Contacto"):
            with st.form("new_contact"):
                n = st.text_input("Nombre"); t = st.text_input("WhatsApp"); tp = st.radio("Tipo", ["Mecánico", "Comercio"])
                if st.form_submit_button("Guardar"):
                    DATA_REF.collection("providers").add({"name":n, "phone":t, "type":tp, "fleetId":u['fleet']})
                    st.rerun()
        
        st.write("### Lista de Contactos")
        for p in providers:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{p['name']}** ({p['type']})")
                c1.caption(f"📱 {p['phone']}")
                c2.link_button("Chat WhatsApp", f"https://wa.me/{p['phone']}")

    if st.sidebar.button("Salir"):
        st.query_params.clear()
        del st.session_state.
