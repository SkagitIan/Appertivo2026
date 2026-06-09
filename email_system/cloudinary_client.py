import hashlib
import logging
import time

import requests
from flask import current_app


logger = logging.getLogger(__name__)


def configured():
    return all(
        current_app.config.get(key)
        for key in ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    )


def _signature(params, api_secret):
    payload = "&".join(f"{key}={params[key]}" for key in sorted(params) if params[key] not in [None, ""])
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()


def enhance_image_url(source_url):
    if not source_url:
        return {"success": False, "image_url": None, "image_path": None, "error": "No image URL was provided."}
    if not configured():
        return {"success": False, "image_url": None, "image_path": None, "error": "Cloudinary is not configured."}

    cloud_name = current_app.config["CLOUDINARY_CLOUD_NAME"]
    api_key = current_app.config["CLOUDINARY_API_KEY"]
    api_secret = current_app.config["CLOUDINARY_API_SECRET"]
    params = {
        "folder": current_app.config.get("CLOUDINARY_FOLDER") or "appertivo/specials",
        "timestamp": int(time.time()),
    }
    payload = {
        **params,
        "api_key": api_key,
        "file": source_url,
        "signature": _signature(params, api_secret),
    }
    try:
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
            data=payload,
            timeout=30,
        )
        data = response.json()
        if not response.ok:
            return {
                "success": False,
                "image_url": None,
                "image_path": None,
                "error": (data.get("error") or {}).get("message", "Cloudinary upload failed."),
            }
        return {
            "success": True,
            "image_url": data.get("secure_url"),
            "image_path": data.get("public_id"),
            "error": None,
        }
    except (requests.RequestException, ValueError) as error:
        logger.exception("Cloudinary image enhancement failed.")
        return {"success": False, "image_url": None, "image_path": None, "error": str(error)}
