from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
META_DIR = DATA_DIR / "meta"
QUEUE_DIR = DATA_DIR / "queue"
OUT_DIR = DATA_DIR / "output"
LOGS_DIR = DATA_DIR / "logs"

for p in (DATA_DIR, JOBS_DIR, META_DIR, QUEUE_DIR, OUT_DIR, LOGS_DIR):
    p.mkdir(parents=True, exist_ok=True)
