#----------------------------------------------------------------------------------------------------
#****************************************************************************************************
#--> CAPTURA DE AUDIO INMP441 (SERVIDOR WEBSOCKET + FASTAPI)
#-->              .: SERVIDOR CENTRAL DE RECEPCION EN LA NUBE:.
#****************************************************************************************************
# Descripcion:
# Este programa es el servidor quien recepcionara los datos provenientes de otros ESP32,
# la raspberry pi sera el cliente de este quien estara conectada a este servidor, los audios
# se guardan temporalemnte en la carpeta del servidor, cada cierto tiempo(1 seg) el cliente(la raspberry) 
# preguntara al servidor si hay nuevos audios y si hay nuevos audios descargara esos audios del servidor para su posterior 
# procesamiento.
# Funciones principales:
#
# 1. Acepta multiples conexiones simultaneas desde dispositivos ESP32
# 2. Escucha transmisiones de audio durante 5 segundos por conexion, de forma concurrente
# 3. Da aviso a la raspberry del audio llegado para que este descargue el audio del servidor
# 4. El servidor siempre esta activo escuchando posibles solicitudes para posteriromente atenderlos.
#-----------------------------------------------------------------------------------------------------

# LIBRERIAS
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import FileResponse
import os
import uuid
import wave
import time
import asyncio

lock = asyncio.Lock()

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
    timestamp: str = Form(...)
):
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

#********************************************************
#--> ROOT
#********************************************************
@app.get("/")
def root():
    return {"estado": "ok"}