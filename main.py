#----------------------------------------------------------------------------------------------------
#****************************************************************************************************
#--> CAPTURA DE AUDIO INMP441 (SERVIDOR WEBSOCKET + FASTAPI)
#-->              .: SERVIDOR CENTRAL DE RECEPCION EN LA NUBE:.
#****************************************************************************************************
# Descripcion:
# Este programa es el servidor quien recepcionara los datos provenientes de otros ESP32,
# la raspberry pi sera el cliente de este quien estarea conectado con websocket, los audios
# se guardan temporalemnte en la carpeta del servidor, la llegada de un nuevo audio implica 
# una alerta para la raspberry quien descargara ese audio del servidor para su posterior 
# procesamiento.
# Funciones principales:
#
# 1. Acepta multiples conexiones simultaneas desde dispositivos ESP32
# 2. Escucha transmisiones de audio durante 5 segundos por conexion, de forma concurrente
# 3. Da aviso a la raspberry del audio llegado para que este descargue el audio del servidor
# 4. El servidor siempre esta activo escuchando posibles solicitudes para posteriromente atenderlos.
#-----------------------------------------------------------------------------------------------------

# LIBRERIAS
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import os
import uuid
import wave

app = FastAPI()

# CARPETA DONDE SE GUARDAN LOS AUDIOS
CARPETA = "grabaciones"
os.makedirs(CARPETA, exist_ok=True)

# HISTORIAL Y CONTADOR
historial = []
contador_id = 0

#********************************************************
#--> RECEPCION DE AUDIOS
#********************************************************
@app.post("/subir-audio/")
async def subir_audio(
    file: UploadFile = File(...),
    dispositivo: str = Form(...),
    timestamp: str = Form(...)
):
    global historial, contador_id

    nombre = f"{uuid.uuid4()}.wav"
    ruta = os.path.join(CARPETA, nombre)

    raw = await file.read()

    # GUARDAR WAV
    with wave.open(ruta, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw)

    # GENERAR ID
    contador_id += 1

    data = {
        "id": contador_id,
        "archivo": nombre,
        "dispositivo": dispositivo,
        "timestamp": timestamp
    }

    historial.append(data)

    print(f"Audio recibido: {data}")

    return {"ok": True, "id": contador_id}


#********************************************************
#--> OBTENER NUEVOS AUDIOS DESDE UN ID
#********************************************************
@app.get("/nuevos/{ultimo_id}")
def get_nuevos(ultimo_id: int):
    nuevos = [a for a in historial if a["id"] > ultimo_id]
    return nuevos


#********************************************************
#--> DESCARGAR AUDIO
#********************************************************
@app.get("/audio/{nombre}")
def get_audio(nombre: str):
    return FileResponse(os.path.join(CARPETA, nombre))


#********************************************************
#--> ROOT
#********************************************************
@app.get("/")
def root():
    return {"estado": "ok"}