from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import whisper
import subprocess
import asyncio
import time
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
model = whisper.load_model("small")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, room: str = ""):
    return templates.TemplateResponse("index.html", {"request": request, "room": room})

@app.post("/rec")
async def start_recording(room: str = Form(...), record: str = Form(...)):
    # Lancer l'enregistrement audio en arrière-plan
    subprocess.Popen(["python3", "publish.py", "--room", room, "--record", record, "--novideo"])

    # Rediriger vers l'URL de visioconférence
    return RedirectResponse(url=f"https://vdo.ninja/?password=false&push={record}&room={room}")

async def stop_recording(record: str):
    # Attendre 1 minute d'inactivité avant d'arrêter l'enregistrement
    await asyncio.sleep(60)

    # Arrêter le processus d'enregistrement
    subprocess.run(["pkill", "-f", f"publish.py --room .* --record {record}"])

    # Transcrire l'audio en texte avec Whisper
    audio_file = f"{record}_*_audio.ts"
    speech = model.transcribe(audio_file, language="fr")['text']

    # Écrire la transcription dans un fichier texte
    with open(f"{record}_speech.txt", "w") as f:
        f.write(speech)

    # Supprimer le fichier audio
    os.remove(audio_file)

@app.post("/stop")
async def stop(record: str = Form(...)):
    # Lancer l'arrêt de l'enregistrement en arrière-plan
    asyncio.create_task(stop_recording(record))
    return {"message": "Recording will stop in 1 minute if idle"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
