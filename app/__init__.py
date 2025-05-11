from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from config import Config
from datetime import datetime, timedelta  # Corrigido aqui
import logging
import os

# Configuração do logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

db = SQLAlchemy()

def create_app():
    """
    Cria e configura a aplicação Flask
    Returns:
        Flask: Aplicação Flask configurada
    """
    try:
        app = Flask(__name__)

        # Carrega configurações do Config
        app.config.from_object(Config)

        # Configurações de segurança
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)  # Corrigido aqui
        app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-size

        # Inicializa SQLAlchemy
        db.init_app(app)

        # Configura pasta de uploads
        uploads_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        app.config['UPLOAD_FOLDER'] = uploads_folder

        # Garante que a pasta de uploads existe
        if not os.path.exists(uploads_folder):
            os.makedirs(uploads_folder)
            logger.info(f"Pasta de uploads criada em: {uploads_folder}")

        # Configura pasta static
        static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        if not os.path.exists(static_folder):
            os.makedirs(static_folder)
            logger.info(f"Pasta static criada em: {static_folder}")

        # Adiciona funções globais para os templates
        @app.context_processor
        def utility_processor():
            """Adiciona funções úteis aos templates"""
            return {
                'now': datetime.now,
                'current_year': datetime.now().year,
                'app_name': 'Automação Magazord',
                'version': '1.0.0'
            }

        # Registra o blueprint
        from app.routes import main
        app.register_blueprint(main)

        # Configura tratamento de erros
        @app.errorhandler(404)
        def not_found_error(error):
            return render_template('errors/404.html'), 404

        @app.errorhandler(500)
        def internal_error(error):
            db.session.rollback()
            return render_template('errors/500.html'), 500

        logger.info("Aplicação Flask inicializada com sucesso")
        return app

    except Exception as e:
        logger.error(f"Erro ao criar aplicação Flask: {e}")
        raise
