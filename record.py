#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import whisper


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
model = whisper.load_model("medium")

PROJECT_DIR = Path(__file__).resolve().parent
TRANSCRIPT_DIR = Path.cwd().resolve() / "stt"
PUBLISH_SCRIPT = PROJECT_DIR / "publish.py"
RECORD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROCESS_TIMEOUT_SECONDS = 3600

# PID -> (process, start time, record ID)
processes = {}
processes_lock = threading.Lock()


def validate_record_id(record: str) -> str:
    if not RECORD_ID_PATTERN.fullmatch(record or ""):
        raise ValueError(
            "Record IDs must be 1-128 characters and contain only letters, "
            "numbers, dots, underscores, or hyphens"
        )
    return record


def start_publish_process(room: str, record: str) -> subprocess.Popen:
    validate_record_id(record)
    process = subprocess.Popen(
        [sys.executable, str(PUBLISH_SCRIPT), "--room", room, "--record", record, "--novideo"],
        cwd=Path.cwd(),
    )
    with processes_lock:
        processes[process.pid] = (process, time.time(), record)
    return process


def terminate_process(process: subprocess.Popen, timeout: float = 10.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def claim_recording_process(process_pid: int, record: str) -> subprocess.Popen | None:
    with processes_lock:
        process_info = processes.get(process_pid)
        if not process_info or process_info[2] != record:
            return None
        del processes[process_pid]
        return process_info[0]


def find_audio_file(record: str) -> Path | None:
    validate_record_id(record)
    matches = list(Path.cwd().glob(f"{record}_*_audio.ts"))
    return max(matches, key=lambda path: path.stat().st_mtime, default=None)


def transcript_path(record: str) -> Path:
    validate_record_id(record)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    return TRANSCRIPT_DIR / f"{record}_speech.txt"


def monitor_processes() -> None:
    while True:
        current_time = time.time()
        expired = []
        with processes_lock:
            for pid, process_info in list(processes.items()):
                process, start_time, _record = process_info
                if process.poll() is not None:
                    del processes[pid]
                elif current_time - start_time > PROCESS_TIMEOUT_SECONDS:
                    expired.append(process)
                    del processes[pid]
        for process in expired:
            logger.info("Terminating process with PID: %d due to timeout", process.pid)
            terminate_process(process)
        time.sleep(60)


monitor_thread = threading.Thread(target=monitor_processes, daemon=True)
monitor_thread.start()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, room: str = "", record: str = ""):
    logger.info("Serving index page with room: %s (%s)", room, record)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "room": room, "record": record},
    )


@app.api_route("/rec", methods=["GET", "POST"])
async def start_recording(request: Request, room: str = Form(None), record: str = Form(None)):
    room = room or request.query_params.get("room")
    record = record or request.query_params.get("record")
    if not room or not record:
        raise HTTPException(status_code=400, detail="Room and record parameters must not be empty")

    try:
        record = validate_record_id(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Starting recording for room: %s with record ID: %s", room, record)
    # Inherit output so logs reach the terminal or systemd journal without blocking a pipe.
    process = start_publish_process(room, record)
    logger.info("Started publish.py process with PID: %d", process.pid)

    return templates.TemplateResponse(
        "recording.html",
        {"request": request, "room": room, "record": record, "process_pid": process.pid},
    )


@app.post("/stop")
async def stop_recording(
    record: str = Form(...),
    process_pid: int = Form(...),
    language: str = Form(...),
):
    try:
        record = validate_record_id(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Stopping recording for record ID: %s with process PID: %d", record, process_pid)
    process = claim_recording_process(process_pid, record)
    if process is None:
        raise HTTPException(status_code=404, detail="Recording process not found")

    await asyncio.to_thread(terminate_process, process)
    logger.info("Stopped publish.py process with PID: %d", process_pid)

    audio_file = find_audio_file(record)
    if audio_file is None:
        logger.error("No audio file found for record ID: %s", record)
        return {"error": f"No audio file found for record ID: {record}"}

    logger.info("Transcribing audio file: %s", audio_file)
    try:
        result = await asyncio.to_thread(model.transcribe, str(audio_file), language=language)
        speech = result["text"]
        logger.info("Transcription completed for record ID: %s", record)
    except Exception as exc:
        logger.error("Failed to transcribe audio file: %s", exc)
        return {"error": f"Failed to transcribe audio file: {exc}"}

    transcript_file = transcript_path(record)
    transcript_file.write_text(speech, encoding="utf-8")
    logger.info("Transcription saved to: %s", transcript_file)

    audio_file.unlink()
    logger.info("Audio file %s removed.", audio_file)
    return {"transcription": speech}


@app.get("/stt")
async def get_transcription(id: str):
    try:
        transcript_file = transcript_path(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not transcript_file.exists():
        logger.error("No transcription file found for record ID: %s", id)
        return JSONResponse(
            status_code=404,
            content={"error": f"No transcription file found for record ID: {id}"},
        )

    transcription = transcript_file.read_text(encoding="utf-8")
    try:
        logger.info("Adding file to IPFS: %s", transcript_file)
        result = subprocess.run(
            ["ipfs", "add", str(transcript_file)],
            capture_output=True,
            text=True,
            check=True,
        )
        cid = result.stdout.split()[1]
        logger.info("Added file to IPFS: %s with CID: %s", transcript_file, cid)
    except Exception as exc:
        logger.error("Failed to add file to IPFS: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to add file to IPFS: {exc}"},
        )

    return {"transcription": transcription, "cid": cid}


def start_recording_cli(room: str, record: str) -> int:
    record = validate_record_id(record)
    logger.info("Starting recording for room: %s with record ID: %s", room, record)
    process = start_publish_process(room, record)
    logger.info("Started publish.py process with PID: %d", process.pid)
    return process.pid


def stop_recording_cli(record: str, process_pid: int, language: str):
    record = validate_record_id(record)
    logger.info("Stopping recording for record ID: %s with process PID: %d", record, process_pid)
    os.kill(process_pid, signal.SIGTERM)
    logger.info("Stopped publish.py process with PID: %d", process_pid)

    audio_file = find_audio_file(record)
    if audio_file is None:
        logger.error("No audio file found for record ID: %s", record)
        return {"error": f"No audio file found for record ID: {record}"}

    logger.info("Transcribing audio file: %s", audio_file)
    try:
        speech = model.transcribe(str(audio_file), language=language)["text"]
        logger.info("Transcription completed for record ID: %s", record)
    except Exception as exc:
        logger.error("Failed to transcribe audio file: %s", exc)
        return {"error": f"Failed to transcribe audio file: {exc}"}

    transcript_file = transcript_path(record)
    transcript_file.write_text(speech, encoding="utf-8")
    logger.info("Transcription saved to: %s", transcript_file)
    audio_file.unlink()
    logger.info("Audio file %s removed.", audio_file)
    return {"transcription": speech}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the FastAPI recording service.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="FastAPI bind address.")
    parser.add_argument("--port", type=int, default=9000, help="FastAPI port.")
    parser.add_argument("--room", type=str, help="Room name for the recording session.")
    parser.add_argument("--record", type=str, help="Record ID for the session.")
    parser.add_argument("--stop", action="store_true", help="Stop the recording.")
    parser.add_argument("--pid", type=int, help="Process PID to stop.")
    parser.add_argument("--language", type=str, default="en", help="Transcription language.")
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
