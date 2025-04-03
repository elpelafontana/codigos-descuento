# main.py
import sqlite3
import string
import random
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

DATABASE = 'discounts.db'

# --- Database Setup ---
def init_db():
    """Crea la tabla si no existe."""
    if not os.path.exists(DATABASE):
        print(f"Creando base de datos en: {DATABASE}")
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        try:
            # Intenta leer el archivo SQL (si lo guardaste)
            # with open('database.sql', 'r') as f:
            #     sql_script = f.read()
            # cursor.executescript(sql_script)

            # O crea la tabla directamente aquí
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                used BOOLEAN NOT NULL DEFAULT 0
            );
            """)
            conn.commit()
            print("Tabla 'discount_codes' creada exitosamente o ya existente.")
        except sqlite3.Error as e:
            print(f"Error al inicializar la base de datos: {e}")
        finally:
            conn.close()
    else:
         print(f"La base de datos '{DATABASE}' ya existe.")


def get_db_connection():
    """Obtiene una conexión a la base de datos."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row # Devuelve filas como diccionarios
    return conn

# --- Helper Functions ---
def generate_random_code(length=10):
    """Genera un código alfanumérico aleatorio en minúsculas."""
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def code_exists(code):
    """Verifica si un código ya existe en la base de datos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM discount_codes WHERE code = ?", (code,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def generate_unique_code():
    """Genera un código único asegurándose que no exista en la DB."""
    while True:
        code = generate_random_code()
        if not code_exists(code):
            return code

# --- Pydantic Models ---
class CodeRequest(BaseModel):
    code: str

# --- FastAPI App ---
app = FastAPI()

# Configurar CORS (para permitir que el frontend React se conecte)
origins = [
    "http://localhost:3000", # Origen de tu app React (ajustá si es necesario)
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"], # Permite todos los headers
)

@app.on_event("startup")
async def startup_event():
    """Inicializa la base de datos al iniciar la API."""
    init_db()

@app.get("/generate_code")
async def get_generate_code():
    """Genera un nuevo código de descuento único."""
    unique_code = generate_unique_code()
    return {"code": unique_code}

@app.post("/grant_code")
async def post_grant_code(payload: CodeRequest):
    """Guarda un código en la base de datos como no usado."""
    code_to_grant = payload.code
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO discount_codes (code, used) VALUES (?, 0)", (code_to_grant,))
        conn.commit()
        return {"message": f"Código '{code_to_grant}' otorgado y guardado exitosamente."}
    except sqlite3.IntegrityError:
        # Esto no debería pasar si se usa generate_unique_code, pero es una salvaguarda
        conn.rollback()
        raise HTTPException(status_code=409, detail=f"El código '{code_to_grant}' ya existe.")
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")
    finally:
        conn.close()

@app.post("/validate_code")
async def post_validate_code(payload: CodeRequest):
    """Valida si un código existe y si está usado."""
    code_to_validate = payload.code
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT used FROM discount_codes WHERE code = ?", (code_to_validate,))
    result = cursor.fetchone()
    conn.close()

    if result is None:
        return {"exists": False, "used": None, "message": f"El código '{code_to_validate}' no existe."}
    else:
        is_used = bool(result['used'])
        status = "usado" if is_used else "no usado"
        return {"exists": True, "used": is_used, "message": f"El código '{code_to_validate}' es válido y está {status}."}

@app.post("/use_code")
async def post_use_code(payload: CodeRequest):
    """Marca un código como usado si existe y no está usado."""
    code_to_use = payload.code
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Verificar si existe y no está usado
        cursor.execute("SELECT used FROM discount_codes WHERE code = ?", (code_to_use,))
        result = cursor.fetchone()

        if result is None:
            raise HTTPException(status_code=404, detail=f"El código '{code_to_use}' no existe.")

        if bool(result['used']):
             raise HTTPException(status_code=409, detail=f"El código '{code_to_use}' ya ha sido usado.")

        # 2. Marcar como usado
        cursor.execute("UPDATE discount_codes SET used = 1 WHERE code = ?", (code_to_use,))
        conn.commit()

        if cursor.rowcount == 0:
             # Esto sería raro si la verificación anterior funcionó, pero por si acaso
             raise HTTPException(status_code=404, detail=f"No se pudo actualizar el código '{code_to_use}' (no encontrado).")

        return {"message": f"Código '{code_to_use}' marcado como usado exitosamente."}
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error de base de datos al usar el código: {e}")
    finally:
        conn.close()

# --- Run the API (optional, for local testing) ---
# if __name__ == "__main__":
#     import uvicorn
#     print("Iniciando servidor FastAPI en http://127.0.0.1:8000")
#     uvicorn.run(app, host="127.0.0.1", port=8000)