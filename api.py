import os
import json
import asyncio
import sys
import io
import zipfile
import shutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from main import _create_initial_state
from graph import build_graph
from tools.logger import get_metrics
from tools.checkpoint import load_checkpoint



# Setup environment path - works in both normal and frozen (PyInstaller) mode
def get_base_path():
    """Get the base path for the application, works in both dev and frozen mode."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_BASE_PATH = get_base_path()
_ENV_PATH = os.path.join(_BASE_PATH, ".env")

import dotenv

dotenv.load_dotenv(_ENV_PATH)

# We set WEB_MODE to signal to graph/nodes that we shouldn't block on stdin
os.environ["AGENTOS_WEB_MODE"] = "1"

app = FastAPI(title="AgentOS UI")

# Mount static directory for the frontend
_STATIC_DIR = os.path.join(_BASE_PATH, "frontend", "dist")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def read_root():
    index_path = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "AgentOS API running. No frontend found at /static/index.html."}


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/favicon.ico")
def read_favicon_ico():
    path = os.path.join(_STATIC_DIR, "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon", headers=_NO_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/favicon.png")
def read_favicon_png():
    path = os.path.join(_STATIC_DIR, "favicon.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png", headers=_NO_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/favicon.svg")
def read_favicon_svg():
    path = os.path.join(_STATIC_DIR, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml", headers=_NO_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/vite.svg")
def read_vite_svg():
    path = os.path.join(_STATIC_DIR, "vite.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml", headers=_NO_CACHE_HEADERS)
    return Response(status_code=404)


class ConfigUpdate(BaseModel):
    keys: dict


@app.get("/api/config")
def get_config():
    """Return configured API keys (masked)"""
    keys = {}
    for k in [
        "GROQ_API_KEY",
        "CEREBRAS_API_KEY",
        "SAMBANOVA_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_AI_API_KEY",
        "FIREWORKS_API_KEY",
        "NOVITA_API_KEY",
        "HF_API_KEY",
    ]:
        val = os.getenv(k, "")
        keys[k] = (
            val
            if val
            and not val.startswith("sk-or-xxxx")
            and not val.startswith("gsk_xxxx")
            else ""
        )
    return {"keys": keys}


@app.post("/api/config")
def update_config(config: ConfigUpdate):
    """Update .env file with new keys"""
    if not os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "w") as f:
            f.write("# AgentOS API Keys\n")

    for k, v in config.keys.items():
        if v and v.strip():
            dotenv.set_key(_ENV_PATH, k, v.strip())
            os.environ[k] = v.strip()
    return {"status": "success"}


@app.get("/api/artifacts")
def get_artifacts():
    """Return all generated files in the output directory."""
    output_dir = os.path.join(_BASE_PATH, "output")
    if not os.path.isdir(output_dir):
        return {"artifacts": {}}

    artifacts = {}
    for root, _, files in os.walk(output_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, output_dir).replace("\\", "/")
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    artifacts[rel_path] = f.read()
            except Exception:
                pass
    return {"artifacts": artifacts}


@app.get("/api/artifacts/download")
def download_artifacts_zip():
    """Download the output directory as a clean ZIP archive."""
    output_dir = os.path.join(_BASE_PATH, "output")
    if not os.path.isdir(output_dir) or not os.listdir(output_dir):
        return JSONResponse({"error": "No output artifacts found to download"}, status_code=404)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(output_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, output_dir).replace("\\", "/")
                zip_file.write(full_path, arcname=rel_path)

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=agentos_project.zip"},
    )


@app.delete("/api/artifacts")
def clear_artifacts():
    """Clear generated files from the output directory."""
    output_dir = os.path.join(_BASE_PATH, "output")
    if os.path.isdir(output_dir):
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    os.remove(item_path)
            except Exception:
                pass
    return {"status": "cleared"}


@app.get("/api/metrics")
def get_pipeline_metrics():
    """Return API and pipeline performance metrics."""
    return {"metrics": get_metrics()}


@app.get("/api/status")
def get_system_status():
    """Return system readiness, Docker status, and active keys."""
    docker_ready = False
    if shutil.which("docker"):
        try:
            import docker
            client = docker.from_env(timeout=2)
            client.ping()
            docker_ready = True
        except Exception:
            docker_ready = False


    configured_keys = [
        k for k in ["GROQ_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY", "OPENROUTER_API_KEY"]
        if os.getenv(k) and not os.getenv(k).startswith("sk-or-xxxx") and not os.getenv(k).startswith("gsk_xxxx")
    ]

    latest_cp = load_checkpoint("latest")
    last_goal = latest_cp.get("goal") if latest_cp else None

    return {
        "docker_available": docker_ready,
        "configured_providers": configured_keys,
        "last_goal": last_goal,
        "status": "ready"
    }



@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio using Groq Whisper-large-v3-turbo for state-of-the-art accuracy."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return JSONResponse({"error": "GROQ_API_KEY not configured", "status": "failed"}, status_code=400)

    try:
        from groq import Groq
        client = Groq(api_key=groq_key)

        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            return {"text": "", "status": "empty"}

        filename = file.filename or "recording.webm"

        transcription = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3-turbo",
            response_format="text",
            prompt="AgentOS, Python, JavaScript, TypeScript, React, FastAPI, Pytest, Docker, API, CLI, algorithm, database, backend, frontend, unit test, build, code, fix",
            temperature=0.0
        )
        text = transcription.strip() if isinstance(transcription, str) else getattr(transcription, "text", str(transcription)).strip()
        return {"text": text, "status": "success"}
    except Exception as e:
        print(f"Transcription error: {e}")
        return JSONResponse({"error": str(e), "status": "failed"}, status_code=500)


import yaml

_MODELS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "models.yaml"
)


@app.get("/api/models")
def get_models():
    """Return available models for each layer"""
    with open(_MODELS_PATH, "r") as f:
        config = yaml.safe_load(f)
    return {"models": config.get("models", {})}


class ModelsUpdate(BaseModel):
    selections: dict  # { task: provider_name }


@app.post("/api/models")
def update_models(update: ModelsUpdate):
    """Update models.yaml to move selected providers to the top of the chain"""
    with open(_MODELS_PATH, "r") as f:
        config = yaml.safe_load(f)

    for task, provider in update.selections.items():
        if task in config["models"]:
            chain = config["models"][task]["chain"]
            # Find the index of the selected provider
            idx = next(
                (i for i, c in enumerate(chain) if c["provider"] == provider), -1
            )
            if idx > 0:
                # Move to top
                item = chain.pop(idx)
                chain.insert(0, item)

    with open(_MODELS_PATH, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    # Invalidate the cached config so the next pipeline run sees the changes
    from config.loader import reload_models

    reload_models()

    return {"status": "success"}


@app.websocket("/api/run")
async def websocket_run(websocket: WebSocket):
    await websocket.accept()

    try:
        # Wait for initial goal message
        data = await websocket.receive_text()
        msg = json.loads(data)
        goal = msg.get("goal")

        if not goal:
            await websocket.send_json({"type": "error", "message": "No goal provided"})
            await websocket.close()
            return

        await websocket.send_json(
            {
                "type": "status",
                "node": "system",
                "message": f"Initializing AgentOS for goal: {goal}",
            }
        )

        state = _create_initial_state(goal)
        graph = build_graph()

        async def execute_pipeline():
            try:
                async for output in graph.astream(state, stream_mode="updates"):
                    for node_name, state_update in output.items():
                        try:
                            await websocket.send_json(
                                {"type": "update", "node": node_name, "state": state_update}
                            )
                        except (TypeError, ValueError) as e:
                            # Fallback: send just the node name without state
                            await websocket.send_json(
                                {"type": "update", "node": node_name, "state": {}}
                            )
                await websocket.send_json(
                    {"type": "done", "message": "Pipeline finished"}
                )
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Graph execution error: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except:
                    pass

        from tools.logger import pop_ui_logs

        async def send_logs():
            try:
                while True:
                    if pipeline_task.done():
                        break
                    logs = pop_ui_logs()
                    for l in logs:
                        await websocket.send_json({"type": "log", "log": l})
                    await asyncio.sleep(0.5)
                # One final drain after pipeline finishes
                logs = pop_ui_logs()
                for l in logs:
                    await websocket.send_json({"type": "log", "log": l})
            except asyncio.CancelledError:
                # Drain any remaining logs before exit
                try:
                    logs = pop_ui_logs()
                    for l in logs:
                        await websocket.send_json({"type": "log", "log": l})
                except Exception:
                    pass
                raise
            except Exception:
                pass

        # Run pipeline as a background task
        pipeline_task = asyncio.create_task(execute_pipeline())
        log_task = asyncio.create_task(send_logs())

        # Wait for client to close the connection (Stop button)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            print("Client disconnected, cancelling pipeline...")
            # Cancel both tasks
            pipeline_task.cancel()
            log_task.cancel()
            # Wait for cancellation to complete with timeout
            try:
                done, pending = await asyncio.wait(
                    [pipeline_task, log_task],
                    timeout=5.0,
                    return_when=asyncio.ALL_COMPLETED,
                )
                # If any still pending after timeout, log warning
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"Task cleanup error: {e}")
            except Exception as e:
                print(f"Error during task cleanup: {e}")

    except WebSocketDisconnect:
        print("Client disconnected during setup")
    except Exception as e:
        print(f"Error in websocket setup: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
