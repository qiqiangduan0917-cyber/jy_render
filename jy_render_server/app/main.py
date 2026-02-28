import sys
import threading
import logging

from fastapi import FastAPI

from app.api import jobs
from app.services.worker import worker_loop
from app.core.logging_config import setup_logging
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

setup_logging()
logger = logging.getLogger(__name__)


app = FastAPI()
app.include_router(jobs.router)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "capcut_render_server is running"}


@app.on_event("startup")
def start_worker():
    t = threading.Thread(target=worker_loop, args=(jobs.load_meta, jobs.save_meta), daemon=True)
    t.start()
