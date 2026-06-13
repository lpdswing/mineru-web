from minio import Minio
import os
from datetime import timedelta
from urllib.parse import urlparse

RAW_MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'mineru-files')
MINIO_REGION = os.getenv('MINIO_REGION', 'us-east-1')


def _parse_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme:
        return parsed.netloc, parsed.scheme == 'https'
    return endpoint, os.getenv('MINIO_SECURE', 'false').lower() == 'true'


MINIO_ENDPOINT, MINIO_SECURE = _parse_endpoint(RAW_MINIO_ENDPOINT)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
    region=MINIO_REGION,
)


def ensure_bucket():
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)


def upload_file(file_obj, filename, content_type=None):
    ensure_bucket()
    minio_path = filename
    minio_client.put_object(
        MINIO_BUCKET,
        minio_path,
        file_obj,
        length=-1,
        part_size=10*1024*1024,
        content_type=content_type
    )
    return minio_path


def get_presigned_url(bucket, minio_path, expires=3600):
    return minio_client.presigned_get_object(bucket, minio_path, expires=timedelta(seconds=expires))


def get_file_url(minio_path, expires=3600):
    return get_presigned_url(MINIO_BUCKET, minio_path, expires=expires)
