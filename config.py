import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or os.urandom(32).hex()
    MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '4' if os.environ.get('VERCEL') else '25'))
    if os.environ.get('VERCEL'):
        MAX_UPLOAD_SIZE_MB = min(MAX_UPLOAD_SIZE_MB, 4)
        MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 256 * 1024
    else:
        MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    BLOB_READ_WRITE_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')
    BLOB_STORE_ID = os.environ.get('BLOB_STORE_ID')
    BLOB_STORAGE_ENABLED = bool(
        BLOB_READ_WRITE_TOKEN
        or (BLOB_STORE_ID and os.environ.get('VERCEL_OIDC_TOKEN'))
    )
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database', 'welding.db'))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))
    INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')
    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm'}
