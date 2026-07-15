"""Photo storage on MinIO (S3-compatible), streamed back through the site."""
import os, io, uuid
import boto3
from botocore.config import Config

BUCKET = os.environ.get("OPDB_S3_BUCKET", "openplantdb-photos")
_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=os.environ["OPDB_S3_ENDPOINT"],
            aws_access_key_id=os.environ["OPDB_S3_KEY"],
            aws_secret_access_key=os.environ["OPDB_S3_SECRET"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic"}


def put(data: bytes, content_type: str, prefix: str = "p") -> str:
    ext = _EXT.get(content_type, "jpg")
    key = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    client().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def get_stream(key: str):
    """Returns (iterator, content_type, length) or raises."""
    obj = client().get_object(Bucket=BUCKET, Key=key)
    return obj["Body"], obj.get("ContentType", "application/octet-stream"), obj.get("ContentLength")
