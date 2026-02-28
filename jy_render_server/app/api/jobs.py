import json
import time
import zipfile
import shutil
from pathlib import Path
import logging

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

from app.core.config import get_config
from app.core.paths import JOBS_DIR, META_DIR, QUEUE_DIR, OUT_DIR

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
cfg = get_config()


logger = logging.getLogger(__name__)


def new_job_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + __import__("uuid").uuid4().hex[:6]


def load_meta(job_id):
    return json.loads((META_DIR / f"{job_id}.json").read_text(encoding="utf-8"))


def save_meta(job_id, meta):
    (META_DIR / f"{job_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


@router.post("")
async def create_job(draft: UploadFile = File(...)):
    job_id = new_job_id()
    logger.info("create_job start job_id=%s filename=%s", job_id, draft.filename)
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)

    zip_path = job_dir / "draft.zip"
    with open(zip_path, "wb") as f:
        while True:
            chunk = await draft.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                continue
            target_path = job_dir / member_path
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(target_path, "wb") as dst:
                dst.write(src.read())

    # flatten single top-level folder (if any)
    top_levels = set()
    has_root_files = False
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            name = member.filename.strip("/")
            if not name:
                continue
            parts = Path(name).parts
            if not member.is_dir() and len(parts) == 1:
                has_root_files = True
                break
            if len(parts) >= 1:
                top_levels.add(parts[0])
    if not has_root_files and len(top_levels) == 1:
        root = job_dir / next(iter(top_levels))
        if root.exists() and root.is_dir():
            for item in root.iterdir():
                target = job_dir / item.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.move(str(item), str(target))
            root.rmdir()

    zip_path.unlink(missing_ok=True)

    logger.info("create_job extracted job_id=%s dir=%s", job_id, job_dir)

    meta = {
        "job_id": job_id,
        "zip_filename": draft.filename,
        "status": "queued",
        "output_path": str(OUT_DIR / f"{job_id}.mp4"),
        "created_at": int(time.time())
    }

    save_meta(job_id, meta)
    (QUEUE_DIR / f"{job_id}.job").write_text(job_id)

    logger.info("create_job queued job_id=%s status=%s", job_id, meta["status"])

    return {
        "code": 0,
        "msg": "success",
        "data": {
            "job_id": job_id,
            "status": "queued"
        }
    }


@router.get("/{job_id}")
def get_job(job_id: str):
    try:
        meta = load_meta(job_id)
    except Exception:
        logger.warning("get_job not_found job_id=%s", job_id)
        return {"code": 40400, "msg": "job not found", "data": None}

    logger.info("get_job job_id=%s status=%s", job_id, meta.get("status"))
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "job_id": meta["job_id"],
            "status": meta["status"]
        }
    }


@router.get("/{job_id}/download")
def download_job(job_id: str):
    logger.info("download_job request job_id=%s", job_id)
    try:
        meta = load_meta(job_id)
    except Exception:
        logger.warning("download_job not_found job_id=%s", job_id)
        return {"code": 40400, "msg": "job not found", "data": None}

    if meta.get("status") != "done":
        logger.warning("download_job not_completed job_id=%s status=%s", job_id, meta.get("status"))
        return {"code": 40900, "msg": "job not completed", "data": None}

    output_path = meta.get("output_path")
    if not output_path:
        logger.error("download_job output_path_missing job_id=%s", job_id)
        return {"code": 40401, "msg": "output not found", "data": None}

    file_path = Path(output_path)
    try:
        file_path.relative_to(OUT_DIR)
    except Exception:
        logger.error("download_job invalid_output_path job_id=%s path=%s", job_id, file_path)
        return {"code": 40300, "msg": "invalid output path", "data": None}

    if not file_path.exists():
        logger.error("download_job output_not_found job_id=%s path=%s", job_id, file_path)
        return {"code": 40401, "msg": "output not found", "data": None}

    logger.info("download_job success job_id=%s path=%s", job_id, file_path)

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"{Path(meta.get('zip_filename', job_id)).stem}.mp4"
    )
