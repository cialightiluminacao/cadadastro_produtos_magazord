import os

class Config:
    SECRET_KEY = '8f42a73e94b1c56d2b32a8b4c7c0f936'  # Chave gerada automaticamente
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    REPORT_FOLDER = os.path.join(os.path.dirname(__file__), 'reports')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
