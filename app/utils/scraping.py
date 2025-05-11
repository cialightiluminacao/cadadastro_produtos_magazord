import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def criar_sessao_requests():
    """
    Cria uma sessão do requests com retry e timeouts adequados
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def limpar_url(url):
    """
    Limpa a URL removendo parâmetros e normalizando
    """
    return url.split('?')[0].rstrip('/')

def extrair_codigo_do_titulo(titulo):
    """
    Extrai o código do produto do final do título
    """
    match = re.search(r'\b(\d+)\s*$', titulo)
    return match.group(1) if match else None

def buscar_titulo_inspirehome(link_base, codigo_produto, max_paginas=30, delay=1):
    """
    Busca o título do produto na InspireHome pelo código do produto
    """
    try:
        codigo_str = str(codigo_produto)
        logger.info(f"Iniciando busca do produto {codigo_str} na InspireHome")

        session = criar_sessao_requests()
        link_base = limpar_url(link_base)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        for pagina in range(1, max_paginas + 1):
            try:
                # Construir URL da página
                url = f"{link_base}?p={pagina}"
                logger.info(f"Verificando página {pagina}: {url}")

                # Fazer requisição
                response = session.get(url, headers=headers, timeout=20)
                response.raise_for_status()

                # Parsear HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # Buscar produtos na página
                produtos = soup.find_all(['div', 'a'], class_=['product-item-info', 'product-item-link'])

                if not produtos:
                    logger.warning(f"Nenhum produto encontrado na página {pagina}")
                    # Verificar se é a última página
                    if not soup.find('a', class_='next'):
                        break
                    continue

                logger.info(f"Encontrados {len(produtos)} produtos na página {pagina}")

                # Verificar cada produto
                for produto in produtos:
                    # Tentar diferentes formas de encontrar o título e link
                    if produto.name == 'div':
                        link_elem = produto.find('a', class_='product-item-link')
                        if not link_elem:
                            continue
                        titulo = link_elem.get_text(strip=True)
                        link = link_elem.get('href')
                    else:  # produto.name == 'a'
                        titulo = produto.get_text(strip=True)
                        link = produto.get('href')

                    if not titulo or not link:
                        continue

                    # Verificar se o código está no título
                    if codigo_str in titulo:
                        logger.info(f"Produto {codigo_str} encontrado!")
                        logger.info(f"Título: {titulo}")
                        logger.info(f"Link: {link}")

                        # Acessar página do produto para confirmar
                        try:
                            prod_response = session.get(link, headers=headers, timeout=20)
                            prod_response.raise_for_status()
                            prod_soup = BeautifulSoup(prod_response.text, 'html.parser')

                            # Tentar pegar o título da página do produto
                            prod_titulo = prod_soup.find('h1', class_='page-title')
                            if prod_titulo:
                                titulo_final = prod_titulo.get_text(strip=True)
                                logger.info(f"Título final confirmado: {titulo_final}")
                                return titulo_final

                            # Se não encontrar o h1, retorna o título original
                            return titulo

                        except Exception as e:
                            logger.error(f"Erro ao acessar página do produto: {e}")
                            return titulo

                # Verificar se tem próxima página
                next_page = soup.find('a', class_='next')
                if not next_page:
                    logger.info("Última página alcançada")
                    break

                # Aguardar entre requisições
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição da página {pagina}: {e}")
                continue
            except Exception as e:
                logger.error(f"Erro inesperado na página {pagina}: {e}")
                continue

        logger.warning(f"Produto {codigo_str} não encontrado após verificar {pagina} páginas")
        return None

    except Exception as e:
        logger.error(f"Erro fatal ao buscar título na InspireHome: {e}")
        return None

def validar_titulo(titulo):
    """
    Valida se o título está no formato esperado
    """
    if not titulo:
        return False

    # Verificar comprimento mínimo
    if len(titulo) < 10:
        return False

    # Verificar se termina com código numérico
    if not re.search(r'\d+\s*$', titulo):
        return False

    return True
