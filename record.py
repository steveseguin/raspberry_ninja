#!/usr/bin/env python3
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import whisper
import subprocess
import os
import logging
import glob
import argparse
import threading
import time
import uvicorn
import shutil

# Configurer la journalisation
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
model = whisper.load_model("small")

# Liste pour suivre les processus
processes = {}

# Fonction pour démarrer un enregistrement
def start_recording(room, record):
    logger.info("Starting recording process for room: %s with record ID: %s", room, record)
    process = subprocess.Popen(["python3", "publish.py", "--room", room, "--record", record, "--novideo"])
    processes[record] = process
    logger.info("Recording process started with PID: %d", process.pid)
    return process

# Fonction pour arrêter un enregistrement
def stop_recording(record):
    process = processes.get(record)
    if process:
        logger.info("Stopping recording process with PID: %d for record ID: %s", process.pid, record)
        process.terminate()
        process.wait()
        del processes[record]
        logger.info("Recording process with PID: %d stopped", process.pid)
    else:
        logger.warning("No recording process found for record ID: %s", record)

# Fonction pour transcrire un segment audio
def transcribe_segment(temp_audio_file, record, language):
    try:
        logger.info("Transcribing audio file: %s for record ID: %s", temp_audio_file, record)
        speech = model.transcribe(temp_audio_file, language=language)['text']
        transcript_file = f"stt/{record}_speech.txt"
        with open(transcript_file, "a") as f:  # Utiliser "a" pour ajouter au fichier existant
            f.write(speech)
        os.remove(temp_audio_file)
        logger.info("Transcription saved to: %s", transcript_file)
        return transcript_file
    except Exception as e:
        logger.error("Failed to transcribe audio file: %s", str(e))
        return None

# Fonction de gestion des enregistrements
def manage_recording(room, record, language, interval=900):  # interval en secondes (900s = 15 minutes)
    while True:
        logger.info("Managing recording for room: %s with record ID: %s", room, record)
        process = start_recording(room, record)
        time.sleep(interval)
        stop_recording(record)
        
        # Déplacer le fichier audio pour transcription
        audio_files = glob.glob(f"{record}_*_audio.ts")
        if audio_files:
            audio_file = audio_files[0]
            temp_audio_file = f"temp_{audio_file}"
            shutil.move(audio_file, temp_audio_file)
            logger.info("Moved audio file to: %s", temp_audio_file)
            
            # Lire le contenu actuel du fichier de transcription
            transcript_file = f"stt/{record}_speech.txt"
            if os.path.exists(transcript_file):
                with open(transcript_file, "r") as f:
                    old_text = f.read()
            else:
                old_text = ""

            # Transcrire le segment audio
            transcribe_segment(temp_audio_file, record, language)

            # Lire le nouveau contenu du fichier de transcription
            with open(transcript_file, "r") as f:
                new_text = f.read()

            # Si aucun nouveau texte n'a été ajouté, arrêter la boucle
            if old_text == new_text:
                logger.info("No new text added for record ID: %s. Stopping recording.", record)
                break
        else:
            logger.warning("No audio file found for record ID: %s", record)
            break

# Fonction pour lister tous les processus en cours
def list_processes():
    logger.info("Listing all recording processes:")
    for record, process in processes.items():
        logger.info("Record ID: %s, PID: %d", record, process.pid)

# Route pour la page d'index
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, room: str = "", record: str = ""):
    logger.info("Serving index page with room: %s (%s)", room, record)
    return templates.TemplateResponse("index.html", {"request": request, "room": room, "record": record})

# Route pour démarrer l'enregistrement
@app.api_route("/rec", methods=["GET", "POST"])
async def start_recording_endpoint(request: Request, room: str = Form(None), record: str = Form(None), language: str = Form("en")):
    room = room or request.query_params.get("room")
    record = record or request.query_params.get("record")
    
    if not room or not record:
        raise HTTPException(status_code=400, detail="Room and record parameters must not be empty")

    logger.info("Starting recording for room: %s with record ID: %s", room, record)
    
    # Démarrer la gestion des enregistrements dans un thread séparé
    manage_thread = threading.Thread(target=manage_recording, args=(room, record, language), daemon=True)
    manage_thread.start()

    return templates.TemplateResponse("recording.html", {"request": request, "room": room, "record": record})

# Route pour arrêter l'enregistrement
@app.post("/stop")
async def stop_recording_endpoint(record: str = Form(...), language: str = Form(...)):
    logger.info("Stopping recording for record ID: %s", record)
    
    # Vérifier l'existence du fichier audio pour identifier l'enregistrement en cours
    audio_files = glob.glob(f"{record}_*_audio.ts")
    if audio_files:
        stop_recording(record)
        audio_file = audio_files[0]
        temp_audio_file = f"temp_{audio_file}"
        shutil.move(audio_file, temp_audio_file)
        logger.info("Moved audio file to: %s", temp_audio_file)
        
        # Transcrire le segment audio
        transcript_file = transcribe_segment(temp_audio_file, record, language)
        if transcript_file:
            with open(transcript_file, "r") as f:
                transcription = f.read()
            logger.info("Returning transcription for record ID: %s", record)
            return {"transcription": transcription}
        else:
            return {"error": "Failed to transcribe audio file"}
    else:
        logger.error("No audio file found for record ID: %s", record)
        return {"error": f"No audio file found for record ID: {record}"}

# Route pour lister tous les processus en cours
@app.get("/list_processes")
async def list_processes_endpoint():
    list_processes()
    return {"message": "Listed all processes in the logs"}

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
        manage_thread = threading.Thread(target=manage_recording, args=(args.room, args.record, args.language), daemon=True)
        manage_thread.start()
        print(f"Recording started for room: {args.room} with record ID: {args.record}")
    elif args.stop and args.record:
        result = stop_recording_endpoint(args.record, args.language)
        print(result)
    else:
        logger.info("Starting FastAPI server")
        uvicorn.run(app, host=args.host, port=args.port)
