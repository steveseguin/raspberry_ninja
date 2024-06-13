#!/usr/bin/env python3
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import whisper
import subprocess
import random
import os
import logging
import glob
import argparse
import threading
import time
import uvicorn 

# Configurer la journalisation
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
model = whisper.load_model("small")

# Liste pour suivre les processus
processes = []

# Fonction de surveillance des processus
def monitor_processes():
    while True:
        current_time = time.time()
        for process_info in processes:
            process, start_time = process_info
            if current_time - start_time > 3600:  # 3600 secondes = 1 heure
                logger.info("Killing process with PID: %d due to timeout", process.pid)
                process.kill()
                processes.remove(process_info)
        time.sleep(60)  # Vérifier toutes les minutes

# Démarrer le thread de surveillance
monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, room: str = "", record: str = ""):
    logger.info("Serving index page with room: %s (%s)", room, record)
    return templates.TemplateResponse("index.html", {"request": request, "room": room, "record": record})

@app.api_route("/rec", methods=["GET", "POST"])
async def start_recording(request: Request, room: str = Form(None), record: str = Form(None)):
    room = room or request.query_params.get("room")
    record = record or request.query_params.get("record")
    
    if not room or not record:
        raise HTTPException(status_code=400, detail="Room and record parameters must not be empty")

    logger.info("Starting recording for room: %s with record ID: %s", room, record)
    
    # Créer un pipe pour rediriger les logs de publish.py
    read_pipe, write_pipe = os.pipe()

    # Lancer l'enregistrement audio en arrière-plan avec les logs redirigés vers le pipe
    process = subprocess.Popen(["python3", "publish.py", "--room", room, "--record", record, "--novideo"], stdout=write_pipe, stderr=write_pipe)
    logger.info("Started publish.py process with PID: %d", process.pid)

    # Fermer le côté écriture du pipe dans le processus parent
    os.close(write_pipe)

    # Ajouter le processus à la liste avec l'heure de début
    processes.append((process, time.time()))

    # Afficher un bouton pour ouvrir la nouvelle page de visioconférence
    return templates.TemplateResponse("recording.html", {"request": request, "room": room, "record": record, "process_pid": process.pid})

@app.post("/stop")
async def stop_recording(record: str = Form(...), process_pid: int = Form(...), language: str = Form(...)):
    logger.info("Stopping recording for record ID: %s with process PID: %d", record, process_pid)
    
    # Arrêter le processus d'enregistrement
    process = subprocess.Popen(["kill", str(process_pid)])
    process.wait()
    logger.info("Stopped publish.py process with PID: %d", process_pid)

    # Trouver le fichier audio correspondant
    audio_files = glob.glob(f"{record}_*_audio.ts")
    if not audio_files:
        logger.error("No audio file found for record ID: %s", record)
        return {"error": f"No audio file found for record ID: {record}"}
    
    audio_file = audio_files[0]
    logger.info("Transcribing audio file: %s", audio_file)
    
    try:
        speech = model.transcribe(audio_file, language=language)['text']
        logger.info("Transcription completed for record ID: %s", record)
    except Exception as e:
        logger.error("Failed to transcribe audio file: %s", str(e))
        return {"error": f"Failed to transcribe audio file: {str(e)}"}

    # Écrire la transcription dans un fichier texte
    transcript_file = f"stt/{record}_speech.txt"
    with open(transcript_file, "w") as f:
        f.write(speech)
    logger.info("Transcription saved to: %s", transcript_file)

    # Supprimer le fichier audio
    os.remove(audio_file)
    logger.info("Audio file %s removed.", audio_file)

    return {"transcription": speech}

def start_recording_cli(room, record):
    logger.info("Starting recording for room: %s with record ID: %s", room, record)
    
    # Créer un pipe pour rediriger les logs de publish.py
    read_pipe, write_pipe = os.pipe()

    # Lancer l'enregistrement audio en arrière-plan avec les logs redirigés vers le pipe
    process = subprocess.Popen(["python3", "publish.py", "--room", room, "--record", record, "--novideo"], stdout=write_pipe, stderr=write_pipe)
    logger.info("Started publish.py process with PID: %d", process.pid)

    # Fermer le côté écriture du pipe dans le processus parent
    os.close(write_pipe)

    # Ajouter le processus à la liste avec l'heure de début
    processes.append((process, time.time()))

    return process.pid

def stop_recording_cli(record, process_pid, language):
    logger.info("Stopping recording for record ID: %s with process PID: %d", record, process_pid)
    
    # Arrêter le processus d'enregistrement
    process = subprocess.Popen(["kill", str(process_pid)])
    process.wait()
    logger.info("Stopped publish.py process with PID: %d", process_pid)

    # Trouver le fichier audio correspondant
    audio_files = glob.glob(f"{record}_*_audio.ts")
    if not audio_files:
        logger.error("No audio file found for record ID: %s", record)
        return {"error": f"No audio file found for record ID: {record}"}
    
    audio_file = audio_files[0]
    logger.info("Transcribing audio file: %s", audio_file)
    
    try:
        speech = model.transcribe(audio_file, language=language)['text']
        logger.info("Transcription completed for record ID: %s", record)
    except Exception as e:
        logger.error("Failed to transcribe audio file: %s", str(e))
        return {"error": f"Failed to transcribe audio file: {str(e)}"}

    # Écrire la transcription dans un fichier texte
    transcript_file = f"stt/{record}_speech.txt"
    with open(transcript_file, "w") as f:
        f.write(speech)
    logger.info("Transcription saved to: %s", transcript_file)

    # Supprimer le fichier audio
    os.remove(audio_file)
    logger.info("Audio file %s removed.", audio_file)

    return {"transcription": speech}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Démarrer le serveur FastAPI avec des paramètres personnalisés.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Adresse hôte pour le serveur FastAPI.")
    parser.add_argument("--port", type=int, default=8000, help="Port pour le serveur FastAPI.")
    parser.add_argument("--room", type=str, help="Room name for the recording session.")
    parser.add_argument("--record", type=str, help="Record ID for the session.")
    parser.add_argument("--stop", action="store_true", help="Stop the recording.")
    parser.add_argument("--pid", type=int, help="Process PID to stop.")
    parser.add_argument("--language", type=str, default="en", help="Language for transcription.")
    args = parser.parse_args()

    if args.room and args.record and not args.stop:
        pid = start_recording_cli(args.room, args.record)
        print(f"Recording started with PID: {pid}")
    elif args.stop and args.pid and args.record:
        result = stop_recording_cli(args.record, args.pid, args.language)
        print(result)
    else:
        logger.info("Starting FastAPI server")
        uvicorn.run(app, host=args.host, port=args.port)
