import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or os.urandom(32).hex()
    MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '25'))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'welding.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')
    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm'}
