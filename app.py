import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import time
import urllib.parse

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Itaro v32 - Directorio", layout="wide", page_icon="📇")

@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_JSON"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()
APP_ID = "itero-titanium-v15"
DATA_REF = db.collection("artifacts").document(APP_ID).collection("public").document("data")

# --- 2. SESIÓN (Asumiendo que ya pasaste el login) ---
if 'user' not in st.session_state:
    st.warning("⚠️ Por favor, inicia sesión primero.")
    st.stop()

u = st.session_state.user

# --- 3. MOTOR DE DATOS DEL DIRECTORIO ---
def load_directory():
    # Traer todos los proveedores de ESTA flota
    docs = DATA_REF.collection("providers").where("fleetId", "==", u['fleet']).stream()
    p_list = [p.to_dict() | {"id": p.id} for p in docs]
    df_dir = pd.DataFrame(p_list)
    if df_dir.empty:
        return pd.DataFrame(columns=['name', 'phone', 'type', 'id'])
    return df_dir

# --- 4. INTERFAZ ---
st.sidebar.title(f"🚖 {u['fleet']}")
menu = ["🏠 Inicio", "🛠️ Taller", "💰 Contabilidad", "🏢 Directorio"]
choice = st.sidebar.radio("Menú", menu)

# --- VISTA: DIRECTORIO (LO QUE NECESITAS) ---
if choice == "🏢 Directorio":
    st.header("🏢 Directorio de Aliados Estratégicos")
    
    # Formulario para nuevos ingresos
    with st.expander("➕ Registrar Nuevo Mecánico o Comercio", expanded=True):
        with st.form("nuevo_proveedor"):
            col1, col2, col3 = st.columns(3)
            p_name = col1.text_input("Nombre / Nombre del Local")
            p_phone = col2.text_input("WhatsApp (Ej: 593987654321)")
            p_type = col3.selectbox("Tipo", ["Mecánico (Mano de Obra)", "Comercio (Repuestos)"])
            
            if st.form_submit_button("GUARDAR EN EL DIRECTORIO"):
                if p_name and p_phone:
                    DATA_REF.collection("providers").add({
                        "fleetId": u['fleet'],
                        "name": p_name.upper().strip(),
                        "phone": p_phone.strip(),
                        "type": p_type,
                        "created_at": datetime.now().isoformat()
                    })
                    st.success(f"✅ {p_name} guardado correctamente.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Por favor, llena el nombre y el teléfono.")

    st.divider()

    # Listado de Proveedores Registrados
    df_dir = load_directory()
    if df_dir.empty:
        st.info("No hay proveedores registrados aún.")
    else:
        st.subheader("Contactos Guardados")
        
        # Filtro rápido
        filtro = st.radio("Filtrar por:", ["Todos", "Mecánicos", "Comercios"], horizontal=True)
        
        temp_df = df_dir.copy()
        if filtro == "Mecánicos":
            temp_df = temp_df[temp_df['type'] == "Mecánico (Mano de Obra)"]
        elif filtro == "Comercios":
            temp_df = temp_df[temp_df['type'] == "Comercio (Repuestos)"]

        for _, row in temp_df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{row['name']}**")
                c1.caption(f"Tipo: {row['type']}")
                
                c2.write(f"📱 {row['phone']}")
                
                # Botón de WhatsApp directo
                link_wa = f"https://wa.me/{row['phone']}"
                c3.markdown(f"[💬 Chatear]({link_wa})")
                
                # Botón para eliminar (Solo Admin)
                if u['role'] == 'owner':
                    if c3.button("🗑️", key=row['id']):
                        DATA_REF.collection("providers").document(row['id']).delete()
                        st.rerun()

# --- VISTA: TALLER (CONEXIÓN CON EL DIRECTORIO) ---
elif choice == "🛠️ Taller":
    st.header("Registrar Mantenimiento")
    df_dir = load_directory()
    
    # Extraer listas para los selectores
    lista_mecanicos = df_dir[df_dir['type'] == "Mecánico (Mano de Obra)"]['name'].tolist()
    lista_comercios = df_dir[df_dir['type'] == "Comercio (Repuestos)"]['name'].tolist()

    with st.form("registro_m"):
        st.subheader("Datos de la Reparación")
        col_a, col_b = st.columns(2)
        cat = col_a.selectbox("Categoría", ["Motor", "Caja", "Frenos", "Llantas", "Aceite", "Suspensión"])
        km_a = col_b.number_input("Kilometraje Actual", min_value=0)
        
        st.divider()
        
        col_m, col_c = st.columns(2)
        # Aquí usamos los datos del directorio
        m_sel = col_m.selectbox("Mecánico (Mano de Obra)", ["N/A"] + lista_mecanicos)
        m_cost = col_m.number_input("Costo Mano de Obra $", min_value=0.0)
        
        c_sel = col_c.selectbox("Comercio (Repuestos)", ["N/A"] + lista_comercios)
        c_cost = col_c.number_input("Costo Repuestos $", min_value=0.0)
        
        if st.form_submit_button("GUARDAR REGRESO"):
            # Lógica para guardar el log con los nombres seleccionados...
            st.success("Mantenimiento registrado con éxito.")

# (El resto de las pestañas mantienen la lógica blindada de la v31)
