#-----------------------------------------------------------------------------------------
#*****************************************************************************************
#--> SERVIDOR CENTRAL DE RECEPCION DE AUDIO (FASTAPI)
#*****************************************************************************************
# Descripcion:
# Servidor encargado de recibir audios desde multiples ESP32, almacenarlos temporalmente
# en formato WAV y gestionar su distribucion a una Raspberry Pi para su procesamiento.
#
# Cada audio incluye metadata como ID unico, dispositivo, timestamp y ubicacion.
# La Raspberry consulta periodicamente al servidor para detectar nuevos audios,
# descargarlos y luego confirmar su recepcion para su eliminacion del sistema.
#
# El servidor soporta multiples conexiones concurrentes y opera de forma continua.
#
# Funciones principales:
# 1. Recepcion de audios desde ESP32
# 2. Registro de metadata (ID, tiempo, ubicacion, dia de la semana)
# 3. Consulta de nuevos audios
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

lock = asyncio.Lock()
semaforo = asyncio.Semaphore(40)

app = FastAPI()

# CARPETA DONDE SE GUARDAN LOS AUDIOS
CARPETA = "grabaciones"
os.makedirs(CARPETA, exist_ok=True)

# HISTORIAL
historial = {}

#************************
#--> RECEPCION DE AUDIOS
#************************
@app.post("/subir-audio/")
async def subir_audio(
    file: UploadFile = File(...),
    dispositivo: str = Form(...),
    timestamp: str = Form(...),
    latitud: float = Form(...),
    longitud: float = Form(...),
    dia_semana: int = Form(...),
):
    async with semaforo:
        global historial

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
            "archivo": nombre,
            "dispositivo": dispositivo,
            "tiempo_evento_ESP32": timestamp,
            "latitud": latitud,
            "longitud": longitud,
            "dia_semana": dia_semana,
            "timestamp": time.time()
        }

        async with lock:
            historial[id_audio] = data

        print(f"Audio recibido: {data}")

        return {"ok": True, "id": data["id"]}


#**************************************
#--> OBTENER NUEVOS AUDIOS DESDE UN ID
#**************************************
@app.get("/nuevos/")
async def get_nuevos(desde: float = 0):
    async with lock:
        nuevos = [a for a in historial.values() if a["timestamp"] > desde]
    return nuevos

#********************
#--> DESCARGAR AUDIO
#********************
@app.get("/audio/{nombre}")
async def get_audio(nombre: str):
    return FileResponse(os.path.join(CARPETA, nombre))

#**************************************
#--> CONFIRMAR DESCARGA Y BORRAR AUDIO
#**************************************
@app.post("/confirmar-audio/")
async def confirmar_audio(data: dict = Body(...)):
    id_audio = data.get("id")

    async with lock:
        audio = historial.get(id_audio)

        if not audio:
            return {"ok": True}

        ruta = os.path.join(CARPETA, audio["archivo"])

        if os.path.exists(ruta):
            os.remove(ruta)

        del historial[id_audio]

    return {"ok": True}

#*********
#--> ROOT
#*********
@app.get("/")
def root():
    return {"estado": "ok"}