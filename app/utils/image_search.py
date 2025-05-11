import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_image_url(id_produto, static_folder):
    """
    Busca a imagem do produto pelo ID no diretório static.
    Tenta diferentes extensões de arquivo (.jpg, .jpeg, .png, .webp).
    Se não encontrar, retorna o caminho da imagem padrão 'blank_1000x1000.png'.

    Args:
        id_produto (str): ID do produto
        static_folder (str): Caminho absoluto para a pasta 'static'

    Returns:
        str: Caminho relativo da imagem para uso no src do HTML
    """
    try:
        # Lista de extensões suportadas
        extensoes = ['.jpg', '.jpeg', '.png', '.webp']
        
        logger.info(f"Buscando imagem para produto {id_produto} em: {static_folder}")

        # Tenta cada extensão
        for ext in extensoes:
            imagem_produto = os.path.join(static_folder, f"{id_produto}{ext}")
            
            if os.path.exists(imagem_produto):
                logger.info(f"Imagem encontrada para produto {id_produto}: {ext}")
                return f"/static/{id_produto}{ext}"

        # Se não encontrou nenhuma imagem
        logger.warning(f"Imagem não encontrada para produto {id_produto}, usando imagem em branco")
        return "/static/blank_1000x1000.png"

    except Exception as e:
        logger.error(f"Erro ao buscar imagem para produto {id_produto}: {e}")
        return "/static/blank_1000x1000.png"
