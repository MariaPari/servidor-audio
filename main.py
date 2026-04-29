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
from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.responses import FileResponse
import os
import uuid
import wave

app = FastAPI()

#********************************************************
#--> CARPETA DONDE SE ALMACENARAN LOS AUDIOS QUE LLEGUEN
#********************************************************
CARPETA = "grabaciones"
os.makedirs(CARPETA, exist_ok=True)

raspberry_ws = None

#*********************************
#--> CONEXION CON LA RASPBERRY PI 
#*********************************
@app.websocket("/ws")
async def ws_raspberry(ws: WebSocket):
    global raspberry_ws
    await ws.accept()
    raspberry_ws = ws
    print("Raspberry conectada")

    try:
        while True:
            await ws.receive_text()
    except:
        raspberry_ws = None
        print("Raspberry desconectada")


#***********************************************************************
#--> FUNCION PARA NOTIFICAR LA LLEGADA DE UN NUEVO AUDIO A LA RASPBERRY
#***********************************************************************
async def notificar(data):
    global raspberry_ws

    if raspberry_ws:
        try:
            await raspberry_ws.send_json(data)
        except:
            raspberry_ws = None


#********************************************************
#--> RECEPCION DE AUDIOS PROVENIENTES DE DISTINTOS ESP32
#********************************************************
@app.post("/subir-audio/")
async def subir_audio(
    file: UploadFile = File(...),               #archivo.wav
    dispositivo: str = Form(...),               #nombre del dispositivo de donde llego el audio
    timestamp: str = Form(...)                  #hora del evento detectado
):

    nombre = f"{uuid.uuid4()}.wav"              #almacenamos el audio con un nombre aleatorio para evitar choques
    ruta = os.path.join(CARPETA, nombre)        #ruta del archivo.wav donde se lo almaceno

    raw = await file.read()

    #convertimos el audio(bytes) a .wav
    with wave.open(ruta, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)      
        wf.setframerate(16000)  
        wf.writeframes(raw)

    print(f"Audio OK {dispositivo} {timestamp}")

    #notificamos la llegada del nuevo audio a la raspberry 
    await notificar({
        "evento": "nuevo_audio",
        "archivo": nombre,
        "dispositivo": dispositivo,
        "timestamp": timestamp
    })

    return {"ok": True, "archivo": nombre}


#*************************************************************
#--> LE PROPORCIONAMOS LA RUTA DEL ARCHIVO.WAV A LA RASPBERRY
#*************************************************************
@app.get("/audio/{nombre}")
def get_audio(nombre: str):
    return FileResponse(os.path.join(CARPETA, nombre))


#**************
#--> CABECERA
#**************
@app.get("/")
def root():
    return {"estado": "ok esta bien"}