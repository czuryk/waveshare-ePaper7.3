#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import logging
import traceback
from datetime import datetime

from io import BytesIO
from PIL import Image, ImageOps
from google import genai

INTERVAL_MINUTES = 1440           # Interval 24hrs
OUT_DIR = "images"
CURRENT_NAME = "current.png"

# Display size h/w
DISPLAY_W = 800
DISPLAY_H = 480

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash-image"
DEFAULT_PROMPT = (
    "Generate horisontal picture for photo frame in sci-fi style"
    "Stylize for e-Ink screen with 4 colors (black, white, red, yellow"
    "High contrash, without text, no logo, no frames"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


# Waveshare lib path
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.exists(LIB_DIR):
    sys.path.append(LIB_DIR)

from waveshare_epd import epd7in3g


def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)


def current_path() -> str:
    return os.path.join(OUT_DIR, CURRENT_NAME)


def archive_current_if_exists():
    cur = current_path()
    if os.path.exists(cur):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        old = os.path.join(OUT_DIR, f"old_{ts}.png")
        os.replace(cur, old)
        logging.info("Archived previous current -> %s", old)


# Adapting picture for 800x480 size
def prepare_for_display(img: Image.Image, w=DISPLAY_W, h=DISPLAY_H) -> Image.Image:
    img = img.convert("RGB")

    iw, ih = img.size
    horizontal = iw >= ih

    if horizontal:
        out = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    else:
        out = ImageOps.contain(img, (w, h), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        x = (w - out.size[0]) // 2
        y = (h - out.size[1]) // 2
        canvas.paste(out, (x, y))
        out = canvas

    return out


# Gemini: generate picture
def generate_image_with_gemini(prompt: str) -> Image.Image:
    api_key = "insear-your-api-key-here"
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt],
    )

    for part in response.parts:
        if part.inline_data is not None:
            data = part.inline_data.data
            if data is None:
                raise RuntimeError("inline_data.data empty.")

            if isinstance(data, str):
                import base64
                data = base64.b64decode(data)

            pil_img = Image.open(BytesIO(data))
            return pil_img.convert("RGB")

    text = []
    for part in response.parts:
        if part.text:
            text.append(part.text)
    raise RuntimeError("Gemini image creation error. Response Text:\n" + "\n".join(text))

def save_current_image(img: Image.Image):
    ensure_dirs()
    archive_current_if_exists()
    path = current_path()
    img.save(path, format="PNG", optimize=True)
    logging.info("Saved current image -> %s (%dx%d)", path, img.size[0], img.size[1])


# E-Ink: Show the image
def display_current_on_epd(epd, img_path: str):
    img = Image.open(img_path).convert("RGB")

    if img.size != (DISPLAY_W, DISPLAY_H):
        img = prepare_for_display(img, DISPLAY_W, DISPLAY_H)

    epd.display(epd.getbuffer(img))
    logging.info("Displayed on EPD: %s", img_path)


def main():
    ensure_dirs()

    epd = epd7in3g.EPD()
    epd.init()
    # epd.Clear()

    if not os.path.exists(current_path()):
        logging.warning("File %s not exist. Put initial picture manualy.", current_path())

    try:
        while True:
            start_ts = time.time()

            try:
                # --- Phase 1: generate picture AI ---
                prompt = DEFAULT_PROMPT
                gen_img = generate_image_with_gemini(prompt)
                prepared = prepare_for_display(gen_img, DISPLAY_W, DISPLAY_H)
                save_current_image(prepared)

            except Exception:
                logging.error("Generation/prepare failed, keeping previous image.\n%s", traceback.format_exc())

            # --- Phase 2: show current.png ---
            try:
                if os.path.exists(current_path()):
                    display_current_on_epd(epd, current_path())
                else:
                    logging.warning("No file %s for displaying.", current_path())
            except Exception:
                logging.error("EPD display failed.\n%s", traceback.format_exc())

            elapsed = time.time() - start_ts
            sleep_s = max(1.0, INTERVAL_MINUTES * 60 - elapsed)
            logging.info("Sleeping %.1f seconds...", sleep_s)
            time.sleep(sleep_s)

    except KeyboardInterrupt:
        logging.info("Interrupted by user (Ctrl+C).")
    finally:
        try:
            epd.sleep()
        except Exception:
            pass
        try:
            epd7in3g.epdconfig.module_exit(cleanup=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()