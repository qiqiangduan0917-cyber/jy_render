import time
import threading
import shutil
from pathlib import Path
import logging

from app.core.config import get_config
from app.core.paths import JOBS_DIR, QUEUE_DIR, OUT_DIR
from app.services.automation import export_one

cfg = get_config()
RENDER_LOCK = threading.Lock()


logger = logging.getLogger(__name__)


def _claim_next_job():
    jobs = sorted(QUEUE_DIR.glob("*.job"), key=lambda p: p.name)
    for job_file in jobs:
        working = job_file.with_suffix(".working")
        try:
            job_file.replace(working)
        except Exception:
            continue
        return working
    return None


def _stage_job_to_capcut(job_id, project_name):
    if not cfg.CAPCUT_PROJECTS_DIR:
        raise RuntimeError("capcut_projects_dir is empty")
    src_dir = JOBS_DIR / job_id
    dst_root = Path(cfg.CAPCUT_PROJECTS_DIR)
    dst_dir = dst_root / project_name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.name in ("meta.json", "worker.log"):
            continue
        target = dst_dir / item.name
        shutil.move(str(item), str(target))
    logger.info("job=%s staged_to=%s", job_id, dst_dir)


def render_job(job_id, load_meta, save_meta):
    meta = load_meta(job_id)
    meta["status"] = "rendering"
    meta["started_at"] = int(time.time())
    save_meta(job_id, meta)

    project_name = job_id
    logger.info(
        "job=%s project_name=%s zip_filename=%s",
        job_id,
        project_name,
        meta.get("zip_filename"),
    )
    _stage_job_to_capcut(job_id, project_name)

    ok = export_one(project_name, cfg, stop_event=None)
    meta["finished_at"] = int(time.time())
    if ok:
        if not cfg.EXPORT_OUTPUT_DIR:
            raise RuntimeError("export_output_dir is empty")
        src_video = Path(cfg.EXPORT_OUTPUT_DIR) / f"{project_name}.mp4"
        dst_video = OUT_DIR / f"{job_id}.mp4"
        if not src_video.exists():
            meta["status"] = "failed"
            meta["error"] = f"exported video not found: {src_video}"
            logger.info("job=%s export_not_found=%s", job_id, src_video)
        else:
            dst_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_video), str(dst_video))
            meta["status"] = "done"
            meta["output_path"] = str(dst_video)
            logger.info("job=%s exported_to=%s", job_id, dst_video)
    else:
        meta["status"] = "failed"
        logger.info("job=%s export_failed", job_id)
    save_meta(job_id, meta)


def worker_loop(load_meta, save_meta):
    print("Worker started...")
    while True:
        working = _claim_next_job()
        if working:
            job_id = working.stem
            try:
                with RENDER_LOCK:
                    render_job(job_id, load_meta, save_meta)
            except Exception as e:
                try:
                    meta = load_meta(job_id)
                    meta["status"] = "failed"
                    meta["error"] = str(e)
                    save_meta(job_id, meta)
                except Exception:
                    pass
                logger.error("job=%s error=%s", job_id, e)
            finally:
                # cleanup job draft and capcut project dir
                try:
                    shutil.rmtree(JOBS_DIR / job_id)
                except Exception:
                    pass
                try:
                    shutil.rmtree(Path(cfg.CAPCUT_PROJECTS_DIR) / job_id)
                    logger.info("草稿删除成功")
                except Exception as e:
                    logger.info("草稿没删除成功",e)
                    pass
                try:
                    working.unlink(missing_ok=True)
                except Exception:
                    pass
        time.sleep(2)
