import requests
from requests.auth import HTTPBasicAuth
import logging
from datetime import datetime
import re
import base64
from io import BytesIO
from PIL import Image
import urllib.request
import os

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Credenciais e URL
usuario = "MZDKbccdfdeadfb29b6ea2186f3db20e3fb04e90c26cbc4845356506eaa5be31"
senha = "uWt3CR%fSz7$"
base_url = "https://cialight.painel.magazord.com.br/api"

class MagazordAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(usuario, senha)
        self.loja_id = 1  # ID da loja
        self.derivacao_id = 3  # ID "Único"
        self.tabela_preco_id = 1  # ID da tabela de preço do site

    def get_marcas(self):
        """Busca todas as marcas cadastradas"""
        try:
            url = f"{base_url}/v2/site/marca"
            response = self.session.get(url)
            response.raise_for_status()
            resposta = response.json()
            marcas = resposta.get("data", {}).get("items", [])
            return [{"id": m.get("id"), "nome": m.get("nome")} for m in marcas]
        except Exception as e:
            logger.error(f"Erro ao buscar marcas: {str(e)}")
            return []

    def get_categorias(self):
        """Busca todas as categorias cadastradas"""
        try:
            url = f"{base_url}/v2/site/categoria"
            response = self.session.get(url)
            response.raise_for_status()
            resposta = response.json()
            categorias = resposta.get("data", {}).get("items", [])
            return [{"id": c.get("id"), "nome": c.get("nome")} for c in categorias]
        except Exception as e:
            logger.error(f"Erro ao buscar categorias: {str(e)}")
            return []

    def get_subcategorias(self, categoria_id):
        """Busca subcategorias de uma categoria específica"""
        try:
            url = f"{base_url}/v2/site/categoria/{categoria_id}/subcategorias"
            response = self.session.get(url)
            response.raise_for_status()
            resposta = response.json()
            subcategorias = resposta.get("data", {}).get("items", [])
            return [{"id": s.get("id"), "nome": s.get("nome")} for s in subcategorias]
        except Exception as e:
            logger.error(f"Erro ao buscar subcategorias da categoria {categoria_id}: {str(e)}")
            return []

    def baixar_e_converter_webp_para_jpg(self, url):
        """
        Baixa uma imagem WebP e converte para JPG em base64
        """
        try:
            # Se a URL começar com 'file://', trata como arquivo local
            if url.startswith('file://'):
                caminho_local = url[7:]  # Remove 'file://'
                with open(caminho_local, 'rb') as f:
                    imagem = Image.open(f)
            else:
                response = urllib.request.urlopen(url)
                imagem = Image.open(BytesIO(response.read()))

            # Converte para RGB se necessário
            if imagem.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', imagem.size, (255, 255, 255))
                background.paste(imagem, mask=imagem.split()[-1])
                imagem = background
            elif imagem.mode != 'RGB':
                imagem = imagem.convert('RGB')

            # Salva em JPG na memória
            buffer = BytesIO()
            imagem.save(buffer, format='JPEG', quality=85)
            imagem_bytes = buffer.getvalue()

            # Converte para base64
            return base64.b64encode(imagem_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Erro ao processar imagem: {str(e)}")
            return None

    def upload_midia(self, nome_arquivo, imagem_base64):
        """
        Faz upload de uma mídia
        """
        try:
            payload = {
                "nome": nome_arquivo,
                "arquivo": imagem_base64,
                "tipo": 1
            }
            response = self.session.post(f"{base_url}/v1/midia", json=payload)
            response.raise_for_status()
            return response.json().get('data', {}).get('id')
        except Exception as e:
            logger.error(f"Erro no upload da mídia: {str(e)}")
            return None

    def associar_midias_produto(self, codigo_produto, midia_ids):
        """
        Associa mídias a um produto
        """
        try:
            payload = {"midias": midia_ids}
            response = self.session.post(
                f"{base_url}/v2/site/produto/{codigo_produto}/midia",
                json=payload
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Erro ao associar mídias: {str(e)}")
            return False

    def gerar_codigos(self, id_produto, prefixo=None):
        """
        Gera códigos pai e filho baseado no ID e prefixo opcional.
        """
        if prefixo:
            codigo_pai = f"P{prefixo}{id_produto}"
            codigo_filho = f"{prefixo}{id_produto}"
        else:
            codigo_pai = f"P{id_produto}"
            codigo_filho = str(id_produto)
        return codigo_pai, codigo_filho

    def tratar_medidas(self, produto):
        """
        Trata todas as medidas do produto.
        """
        medidas = {
            'peso': produto.get('peso', 1.000),
            'altura': produto.get('altura', 10),
            'largura': produto.get('largura', 10),
            'comprimento': produto.get('comprimento', 10)
        }

        # Converte valores para float
        return {k: float(str(v).replace(',', '.')) if isinstance(v, (str, int, float)) else float(1.0)
                for k, v in medidas.items()}

    def cadastrar_produto(self, produto, prefixo=None):
        """
        Cadastra um produto completo (pai e filho) na Magazord.
        """
        try:
            # Gera códigos pai e filho
            codigo_pai, codigo_filho = self.gerar_codigos(produto['id'], prefixo)

            # Verifica se o produto já existe
            try:
                verificacao = self.session.get(f"{base_url}/v2/site/produto/{codigo_pai}")
                if verificacao.status_code == 200:
                    return False, f"Produto {codigo_pai} já existe no sistema"
            except:
                pass  # Se der erro na verificação, tenta cadastrar mesmo assim

            # Data de lançamento
            data_lancamento = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-03:00")

            # Trata as medidas
            medidas = self.tratar_medidas(produto)

            # Trata o preço
            try:
                preco_venda = float(str(produto.get('preco_venda', '0')).replace(',', '.'))
                if preco_venda <= 0:
                    preco_venda = 100.00  # Preço padrão caso não encontre
                preco_antigo = round(preco_venda * 1.2, 2)  # 20% maior
                percentual_desconto = round(((preco_antigo - preco_venda) / preco_antigo) * 100, 2)
            except:
                preco_venda = 100.00
                preco_antigo = 120.00
                percentual_desconto = 16.67

            # Trata o EAN
            ean = str(produto.get('ean', '')).strip()
            if ean.lower() in ['nan', 'none', '']:
                ean = ''

            # Monta payload do produto pai
            payload_pai = {
                "codigo": codigo_pai,
                "nome": produto['titulo'],
                "descricao": produto.get('descricao', ''),
                "marca": int(produto['marca_id']),
                "categorias": [int(produto['categoria_id'])] if produto.get('categoria_id') else [],
                "peso": medidas['peso'],
                "altura": medidas['altura'],
                "largura": medidas['largura'],
                "comprimento": medidas['comprimento'],
                "ativo": True,
                "destaque": True,
                "tipo": 1,
                "unidadeMedida": "UN",
                "garantia": 12,
                "ncm": produto.get('ncm', "94051099"),
                "origemFiscal": int(produto.get('origem_fiscal', 0)),
                "gtin": ean,
                "gtinEmbalagem": "",
                "tipoEmbalagem": 1,
                "volumes": 1,
                "dataLancamento": data_lancamento,
                "produtoLoja": [
                    {
                        "loja": self.loja_id,
                        "ativo": True
                    }
                ],
                "metaTitle": produto['titulo'],
                "metaDescription": f"{produto['titulo']}. Design moderno, iluminação eficiente e acabamento premium. Compre na Cialight.",
                "palavrasChave": ["pendente led", "iluminação", "luminária", produto.get('cor', '').lower()],
                "acompanha": "Manual de instalação, kit de fixação",
                "caracteristicas": [
                    {"nome": "Potência", "valor": produto.get('potencia', '')},
                    {"nome": "Temperatura de cor", "valor": produto.get('temperatura_cor', '')},
                    {"nome": "Material", "valor": "Alumínio"},
                    {"nome": "Lúmens", "valor": str(produto.get('lumens', ''))},
                    {"nome": "IP", "valor": produto.get('ip', '')},
                    {"nome": "Tensão", "valor": produto.get('tensao', 'Bivolt')},
                    {"nome": "Cor", "valor": produto.get('cor', '')}
                ],
                "derivacoes": [self.derivacao_id]  # ID 3 para "Único"
            }

            # 1. Cadastrar produto pai
            logger.info(f"Cadastrando produto pai {codigo_pai}...")
            response = self.session.post(
                f"{base_url}/v2/site/produto",
                json=payload_pai
            )
            response.raise_for_status()

            if response.status_code in [200, 201]:
                # 2. Upload e associação de imagens
                if produto.get('img_url'):
                    # Corrige o caminho da imagem se for relativo
                    img_url = produto['img_url']
                    if img_url.startswith('/'):
                        img_url = f"file://{os.path.abspath(os.path.join(os.getcwd(), 'app', img_url.lstrip('/')))}"

                    imagem_base64 = self.baixar_e_converter_webp_para_jpg(img_url)
                    if imagem_base64:
                        midia_id = self.upload_midia(
                            f"{codigo_filho}.jpg",
                            imagem_base64
                        )
                        if midia_id:
                            self.associar_midias_produto(codigo_pai, [midia_id])

                # 3. Cadastrar derivação (produto filho)
                derivacao_payload = {
                    "codigo": codigo_filho,
                    "peso": medidas['peso'],
                    "altura": medidas['altura'],
                    "largura": medidas['largura'],
                    "comprimento": medidas['comprimento'],
                    "ativo": True,
                    "dataLancamento": data_lancamento,
                    "derivacoes": [
                        {
                            "derivacao": self.derivacao_id,
                            "valor": "Único"
                        }
                    ],
                    "lojas": [self.loja_id]
                }

                response_derivacao = self.session.post(
                    f"{base_url}/v2/site/produto/{codigo_pai}/derivacao",
                    json=derivacao_payload
                )
                response_derivacao.raise_for_status()

                if response_derivacao.status_code in [200, 201]:
                    # 4. Cadastrar preço
                    preco_data = [{
                        "produto": codigo_filho,
                        "tabelaPreco": self.tabela_preco_id,
                        "precoVenda": preco_venda,
                        "precoAntigo": preco_antigo,
                        "percentualDesconto": percentual_desconto
                    }]

                    response_preco = self.session.post(
                        f"{base_url}/v1/preco",
                        json=preco_data
                    )
                    response_preco.raise_for_status()

                    # 5. Cadastrar estoque
                    estoque_data = {
                        "produto": codigo_filho,
                        "deposito": 1,
                        "quantidade": 10,
                        "tipo": 1,
                        "tipoOperacao": 1,
                        "origemMovimento": 1
                    }

                    response_estoque = self.session.post(
                        f"{base_url}/v1/estoque",
                        json=estoque_data
                    )
                    response_estoque.raise_for_status()

                    return True, {
                        'codigo_pai': codigo_pai,
                        'codigo_filho': codigo_filho,
                        'response': response.json()
                    }

            return False, "Erro ao cadastrar produto"

        except Exception as e:
            logger.error(f"Erro ao cadastrar produto: {str(e)}")
            return False, str(e)
