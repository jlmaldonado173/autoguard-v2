import customtkinter as ctk
import firebase_admin
from firebase_admin import credentials, firestore

# 1. CONEXIÓN A FIREBASE
archivo_llave = "miflota-30356-firebase-adminsdk-fbsvc-cf539b2574.json"

try:
    cred = credentials.Certificate(archivo_llave)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Conexión exitosa a MiFlota")
except Exception as e:
    print(f"❌ Error: Asegúrate de que el archivo JSON esté en la carpeta: {e}")

# 2. INTERFAZ DE AUTOGUARD AI
class AutoGuardApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AutoGuard AI - Gestión de Flota")
        self.geometry("900x600")

        # Sidebar para navegación
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        
        self.lbl_titulo = ctk.CTkLabel(self.sidebar, text="AUTO GUARD AI", font=("Arial", 20, "bold"))
        self.lbl_titulo.pack(pady=20, padx=10)

        # Botones del menú (Combustible, Analytics, etc.)
        self.btn_combustible = ctk.CTkButton(self.sidebar, text="Carga de Combustible")
        self.btn_combustible.pack(pady=10, padx=10)
        
        self.btn_excel = ctk.CTkButton(self.sidebar, text="Descargar Excel", fg_color="green")
        self.btn_excel.pack(pady=10, padx=10)

        # Contenedor Principal
        self.main_frame = ctk.CTkFrame(self, corner_radius=15)
        self.main_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        
        self.lbl_bienvenida = ctk.CTkLabel(self.main_frame, text="Bienvenido al Dashboard", font=("Arial", 24))
        self.lbl_bienvenida.pack(pady=20)

if __name__ == "__main__":
    app = AutoGuardApp()
    app.mainloop()