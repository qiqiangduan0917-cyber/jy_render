import time
import random
import logging

import pyautogui
from PIL import Image

pyautogui.FAILSAFE = True

OFFSET_RANGE = 5

logger = logging.getLogger(__name__)


def _rand_offset(x, y):
    dx = random.randint(-OFFSET_RANGE, OFFSET_RANGE)
    dy = random.randint(-OFFSET_RANGE, OFFSET_RANGE)
    return x + dx, y + dy


def _stopped(stop_event):
    return stop_event is not None and stop_event.is_set()


def click_template(template_path: str, confidence: float = 0.8,
                   stop_event=None, timeout: int = 30,
                   interval: float = 0.5) -> bool:
    if _stopped(stop_event):
        return False
    template_image = Image.open(template_path)
    elapsed = 0.0
    while elapsed < timeout:
        if _stopped(stop_event):
            return False
        time.sleep(interval)
        elapsed += interval
        try:
            box = pyautogui.locateOnScreen(template_image, confidence=confidence)
        except Exception:
            box = None
        if box is None:
            continue
        x, y = pyautogui.center(box)
        x, y = _rand_offset(x, y)
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.click()
        logger.info("  [click] %s -> (%s, %s)", template_path, x, y)
        return True
    logger.info("  [timeout] %ss not found: %s", timeout, template_path)
    return False


def try_click(template_path: str, stop_event=None) -> bool:
    if click_template(template_path, 0.8, stop_event=stop_event):
        return True
    return click_template(template_path, 0.7, stop_event=stop_event)


def wait_for_template(template_path: str, timeout: int = 300,
                      interval: int = 3, stop_event=None) -> bool:
    logger.info("  [wait] %s (%ss)", template_path, timeout)
    template_image = Image.open(template_path)
    elapsed = 0
    while elapsed < timeout:
        if _stopped(stop_event):
            logger.info("  [stop] cancel by stop_event")
            return False
        try:
            box = pyautogui.locateOnScreen(template_image, confidence=0.8)
        except Exception:
            box = None
        if box is not None:
            logger.info("  [found] %ss", elapsed)
            return True
        time.sleep(interval)
        elapsed += interval
    logger.info("  [timeout] %ss not found", timeout)
    return False


def wait_for_template_disappear(template_path: str, timeout: int = 60,
                                interval: int = 1, stop_event=None) -> bool:
    logger.info("  [wait disappear] %s (%ss)", template_path, timeout)
    template_image = Image.open(template_path)
    elapsed = 0
    while elapsed < timeout:
        if _stopped(stop_event):
            logger.info("  [stop] cancel by stop_event")
            return False
        try:
            box = pyautogui.locateOnScreen(template_image, confidence=0.8)
        except Exception:
            box = None
        if box is None:
            logger.info("  [disappear] %ss", elapsed)
            return True
        time.sleep(interval)
        elapsed += interval
    logger.info("  [timeout] still exists: %s", template_path)
    return False


def wait_loading_if_appears(cfg, stop_event=None) -> bool:
    template_path = cfg.LOADING_IMG
    logger.info("  [check loading] %s", template_path)

    template_image = Image.open(template_path)
    elapsed = 0
    appear_timeout = 0
    interval = 1

    while elapsed < appear_timeout:
        if _stopped(stop_event):
            logger.info("  [stop] cancel by stop_event")
            return False
        try:
            box = pyautogui.locateOnScreen(template_image, confidence=0.8)
        except Exception:
            box = None
        if box is not None:
            logger.info("  [loading appear] wait disappear")
            return wait_for_template_disappear(
                template_path, timeout=60, interval=1, stop_event=stop_event
            )
        time.sleep(interval)
        elapsed += interval

    logger.info("  [loading not appear] continue")
    return True


def export_one(name: str, cfg, stop_event=None) -> bool:
    if _stopped(stop_event):
        return False

    logger.info("\n%s", "=" * 50)
    logger.info("  Export project: %s", name)
    logger.info("%s", "=" * 50)

    steps = [
        ("search", lambda: try_click(cfg.SEARCH_BTN, stop_event=stop_event)),
        ("type name", lambda: _type_text(name)),
        ("click result", lambda: _click_pos(cfg.SEARCH_RESULT_X, cfg.SEARCH_RESULT_Y)),
        ("wait loading disappear", lambda: wait_loading_if_appears(cfg, stop_event=stop_event)),
        ("export", lambda: try_click(cfg.EXPORT_BTN, stop_event=stop_event)),
        ("confirm export", lambda: try_click(cfg.DO_EXPORT_BTN, stop_event=stop_event)),
        ("wait publish", lambda: wait_for_template(
            cfg.PUBLISH_BTN, cfg.EXPORT_TIMEOUT, cfg.POLL_INTERVAL,
            stop_event=stop_event)),
        ("cancel", lambda: try_click(cfg.CANCEL_BTN, stop_event=stop_event)),
        ("home", lambda: try_click(cfg.HOME_BTN, stop_event=stop_event)),
        ("restore", lambda: try_click(cfg.RESTORE_BTN, stop_event=stop_event)),
    ]

    for step_name, action in steps:
        if _stopped(stop_event):
            logger.info("  [stop] cancel by stop_event")
            return False
        time.sleep(2)
        if not action():
            logger.info("  [failed] %s: %s", step_name, name)
            return False
        logger.info("  [ok] %s", step_name)

    logger.info("  [%s] done", name)
    return True


def _type_text(text: str) -> bool:
    pyautogui.typewrite(text, interval=0.05)
    return True


def _click_pos(x: int, y: int) -> bool:
    x, y = _rand_offset(x, y)
    pyautogui.moveTo(x, y, duration=0.3)
    pyautogui.click()
    return True



