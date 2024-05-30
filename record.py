#!/usr/bin/env python3
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import whisper
import subprocess
import asyncio
import time
import random
import sys
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
model = whisper.load_model("small")

def generate_record_id():
    # Generate and return a unique record ID
    return str(random.randint(1000000, 9999999))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, room: str = ""):
    return templates.TemplateResponse("index.html", {"request": request, "room": room, "generate_record_id": generate_record_id})

@app.post("/rec")
async def start_recording(room: str = Form(...), record: str = Form(...)):
    # Créer un pipe pour rediriger les logs de publish.py
    read_pipe, write_pipe = os.pipe()

    # Lancer l'enregistrement audio en arrière-plan avec les logs redirigés vers le pipe
    process = subprocess.Popen(["python3", "publish.py", "--room", room, "--record", record, "--novideo"], stdout=write_pipe, stderr=write_pipe)

    # Fermer le côté écriture du pipe dans le processus parent
    os.close(write_pipe)

    # Lancer une tâche en arrière-plan pour surveiller les logs et arrêter l'enregistrement
    asyncio.create_task(stop_recording(process, read_pipe, record))

    # Rediriger vers l'URL de visioconférence
    return RedirectResponse(url=f"https://vdo.ninja/?password=false&push={record}&room={room}")

async def stop_recording(process, read_pipe, record):
    # Lire les logs de publish.py à partir du pipe
    with os.fdopen(read_pipe) as pipe:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, pipe.readline)
            if "DATA CHANNEL: CLOSE" in line:
                break

    # Arrêter le processus d'enregistrement
    process.terminate()
    process.wait()

    # Transcrire l'audio en texte avec Whisper
    audio_file = f"{record}_*_audio.ts"
    speech = model.transcribe(audio_file, language="fr")['text']

    # Écrire la transcription dans un fichier texte
    with open(f"stt/{record}_speech.txt", "w") as f:
        f.write(speech)

    # Supprimer le fichier audio
    os.remove(audio_file)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
