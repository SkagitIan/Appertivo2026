from pathlib import Path
from uuid import uuid4

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class UploadError(ValueError):
    pass


def validate_image(upload):
    if not upload or not upload.filename:
        return None
    extension = ALLOWED_IMAGE_TYPES.get(upload.mimetype)
    if not extension:
        raise UploadError("Photo must be a JPEG, PNG, or WebP image.")
    return f"specials/{uuid4().hex}{extension}"


class LocalStorage:
    def __init__(self, upload_root, public_base_url="/uploads"):
        self.upload_root = Path(upload_root)
        self.public_base_url = public_base_url.rstrip("/")

    def save(self, upload, object_key):
        destination = self.upload_root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        upload.save(destination)
        return object_key, f"{self.public_base_url}/{object_key}"


class R2Storage:
    def __init__(self, endpoint, bucket, access_key, secret_key, public_base_url):
        import boto3

        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")
        self.client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )

    def save(self, upload, object_key):
        self.client.upload_fileobj(
            upload.stream,
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": upload.mimetype},
        )
        return object_key, f"{self.public_base_url}/{object_key}"


def build_storage(app):
    if app.config.get("R2_ENDPOINT"):
        return R2Storage(
            app.config["R2_ENDPOINT"],
            app.config["R2_BUCKET"],
            app.config["R2_ACCESS_KEY_ID"],
            app.config["R2_SECRET_ACCESS_KEY"],
            app.config["R2_PUBLIC_BASE_URL"],
        )
    return LocalStorage(app.config["UPLOAD_ROOT"])


def save_special_photo(app, upload):
    object_key = validate_image(upload)
    if not object_key:
        return None, None
    return build_storage(app).save(upload, object_key)
