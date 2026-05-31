#-----------------------------------------------------------------------------------------
#*****************************************************************************************
#--> SERVIDOR CENTRAL DE RECEPCION DE AUDIO E IMAGEN (FASTAPI)
#*****************************************************************************************
# Descripcion:
# Servidor encargado de recibir audios e imagenes desde multiples ESP32, almacenarlos 
# temporalmente en formato WAV para audios y formato .jpg para imagenes
# y gestionar su distribucion a una Raspberry Pi para su procesamiento.
#
# Cada audio incluye metadata como ID unico, dispositivo, timestamp y ubicacion.
# La Raspberry consulta periodicamente al servidor para detectar nuevos audios,
# descargarlos y luego confirmar su recepcion para su eliminacion del sistema, de igual
# forma para las imagenes se tendra un ID unico, dispositivo, timestamp.
#
# El servidor soporta multiples conexiones concurrentes y opera de forma continua.
#
# Funciones principales:
# 1. Recepcion de audios e imagenes desde ESP32
# 2. Registro de metadata (ID, tiempo, ubicacion, dia de la semana)
# 3. Consulta de nuevos audios e imagenes
# 4. Descarga de archivos
# 5. Eliminacion tras confirmacion
#------------------------------------------------------------------------------------------

#*********************
#--> LIBRERIAS USADAS
#*********************
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import FileResponse
import os
import uuid
import wave
import time
import asyncio
from typing import Optional
import asyncpg

lock = asyncio.Lock()
semaforo = asyncio.Semaphore(30)

app = FastAPI()

# CARPETA DONDE SE GUARDAN LOS AUDIOS
CARPETA = "grabaciones"
os.makedirs(CARPETA, exist_ok=True)

# CARPETA DONDE SE GUARDAN LAS IMAGENES
CARPETA_IMAGENES = "imagenes"
os.makedirs(CARPETA_IMAGENES, exist_ok=True)

#**************************************************
#--> FUNCION PARA LA CONEXION CON LA BASE DE DATOS
#**************************************************
pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        host="db.vlhsalxncoicavjuerbc.supabase.co",
        database="postgres",
        user="postgres",
        password="audienciaTV2026MP",
        port=5432,
        min_size=5,
        max_size=20
    )

#***************************************************************************************************************************************
#--> FUNCION PARA ACTUALIZAR LOS DATOS DE LOS DISPOSITIVOS QUE LLEGUEN (SOLO SE ATENDERA AQUELLOS DISPOSITIVOS PREVIAMENTE REGISTRADOS)
#    , SI EL DISPOSITIVO NO FUE REGISTRADO ENTONCES SE IGNORA TAL DISPOSITIVO
#***************************************************************************************************************************************
async def dispositivo_registrado(dispositivo):
    async with pool.acquire() as conn:

        fila = await conn.fetchrow(
            """
            SELECT dispositivo_tv
            FROM dispositivos_tv_estudio
            WHERE dispositivo_tv = $1
            """,
            dispositivo
        )
        return fila is not None
    
async def actualizar_dispositivo(dispositivo,latitud,longitud,estado_tv,estado_sensores):
    async with pool.acquire() as conn:

        resultado = await conn.execute(
            """
            UPDATE dispositivos_tv_estudio
            SET
                latitud = $1,
                longitud = $2,
                estado_tv = $3,
                estado_sensores = $4
            WHERE dispositivo_tv = $5
            """,
            latitud,
            longitud,
            estado_tv,
            estado_sensores,
            dispositivo
        )

        if resultado == "UPDATE 0":
            print(f"Dispositivo no registrado: {dispositivo}")
            return False

        print(f"Dispositivo actualizado: {dispositivo}")
        return True

# HISTORIAL
historial = {}

#************************
#--> RECEPCION DE AUDIOS
#************************
@app.post("/subir-audio/")
async def subir_audio(
    file: UploadFile = File(...),
    dispositivo: str = Form(...),
    latitud: float = Form(...),
    longitud: float = Form(...),
    dia_semana: int = Form(...),
    estado_tv: bool = Form(...),
    estado_sensores: int = Form(...)
):
    # Verificamos que el dispositivo existe y actualizar datos
    actualizado = await actualizar_dispositivo(dispositivo,latitud,longitud,estado_tv,estado_sensores)
    if not actualizado:
        return {
            "ok": False,
            "error": "Dispositivo no registrado"
        }

    async with semaforo:
        id_audio = str(uuid.uuid4())

        nombre = f"{id_audio}.wav"
        ruta = os.path.join(CARPETA, nombre)

        raw = await file.read()

        # GUARDAR WAV
        with wave.open(ruta, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(raw)

        data = {
            "id": id_audio,
            "tipo": "audio",
            "archivo": nombre,
            "dispositivo": dispositivo,
            "dia_semana": dia_semana,
            "timestamp": time.time()
        }

        async with lock:
            historial[id_audio] = data

        print(f"Audio recibido: {data}")

        return {"ok": True, "id": data["id"]}

#**************************
#--> RECEPCION DE IMAGENES
#**************************
@app.post("/subir-imagen/")
async def subir_imagen(
    file: UploadFile = File(...),
    dispositivo: str = Form(...),
):
    # Verificamos que el dispositivo existe
    if not await dispositivo_registrado(dispositivo):
        return {
            "ok": False,
            "error": "Dispositivo no registrado"
        }
    
    async with semaforo:
        id_imagen = str(uuid.uuid4())

        extension = "jpg"
        if file.filename and "." in file.filename:
            extension = file.filename.split(".")[-1]
        nombre = f"{id_imagen}.{extension}"

        ruta = os.path.join(CARPETA_IMAGENES, nombre)

        contenido = await file.read()

        with open(ruta, "wb") as f:
            f.write(contenido)

        data = {
            "id": id_imagen,
            "tipo": "imagen",
            "archivo": nombre,
            "dispositivo": dispositivo,
            "timestamp": time.time()
        }

        async with lock:
            historial[id_imagen] = data

        print(f"Imagen recibida: {data}")

        return {"ok": True, "id": data["id"]}
    
#*************************************************
#--> OBTENER NUEVOS AUDIOS E IMAGENES DESDE UN ID
#*************************************************
@app.get("/nuevos/")
async def get_nuevos(desde: float = 0,tipo: Optional[str] = None):
    if tipo not in [None, "audio", "imagen"]:
        return {"error": "tipo invalido"}
    async with lock:
        nuevos = [a for a in historial.values() if a["timestamp"] > desde and (tipo is None or a["tipo"] == tipo)]
    return nuevos

#********************
#--> DESCARGAR AUDIO
#********************
@app.get("/audio/{nombre}")
async def get_audio(nombre: str):
    nombre = os.path.basename(nombre)
    return FileResponse(os.path.join(CARPETA, nombre),media_type="audio/wav")

#**********************
#--> DESCARGAR IMAGEN
#**********************
@app.get("/imagen/{nombre}")
async def get_imagen(nombre: str):
    nombre = os.path.basename(nombre)
    return FileResponse(os.path.join(CARPETA_IMAGENES, nombre),media_type="image/jpeg")

#***********************************************
#--> CONFIRMAR DESCARGA Y BORRAR AUDIO E IMAGEN
#***********************************************
@app.post("/confirmar/")
async def confirmar_archivo(data: dict = Body(...)):
    id_audio = data.get("id")

    async with lock:
        audio = historial.get(id_audio)

        if not audio:
            return {"ok": True}

        if audio["tipo"] == "audio":
            ruta = os.path.join(CARPETA, audio["archivo"])
        else:
            ruta = os.path.join(CARPETA_IMAGENES, audio["archivo"])

        if os.path.exists(ruta):
            os.remove(ruta)

        del historial[id_audio]

    return {"ok": True}

#******************************
#--> CERRAMOS LA CONEXION POOL
#******************************
@app.on_event("shutdown")
async def shutdown():
    await pool.close()
    print("Pool PostgreSQL cerrado")

#*********
#--> ROOT
#*********
@app.get("/")
def root():
    return {"estado": "ok"}