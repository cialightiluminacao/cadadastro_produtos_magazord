import requests
from requests.auth import HTTPBasicAuth
import logging
from datetime import datetime
import re

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Credenciais e URL
usuario = "MZDKbccdfdeadfb29b6ea2186f3db20e3fb04e90c26cbc4845356506eaa5be31"
senha = "uWt3CR%fSz7$"
base_url = "https://cialight.painel.magazord.com.br"

def limpar_numero(valor):
    """
    Remove caracteres não numéricos e converte para float.

    Args:
        valor: Valor a ser convertido (str, int, float ou None)

    Returns:
        float: Valor convertido ou 0.0 se inválido
    """
    if valor is None:
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    if isinstance(valor, str):
        # Remove tudo que não for número, ponto ou vírgula
        valor = valor.replace(',', '.')
        valor = re.sub(r'[^\d.]', '', valor)

        if valor:
            try:
                return float(valor)
            except ValueError:
                logger.warning(f"Não foi possível converter '{valor}' para número")
                return 0.0
    return 0.0

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
            url = f"{base_url}/api/v2/site/marca"
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
            url = f"{base_url}/api/v2/site/categoria"
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
            url = f"{base_url}/api/v2/site/categoria/{categoria_id}/subcategorias"
            response = self.session.get(url)
            response.raise_for_status()
            resposta = response.json()
            subcategorias = resposta.get("data", {}).get("items", [])
            return [{"id": s.get("id"), "nome": s.get("nome")} for s in subcategorias]
        except Exception as e:
            logger.error(f"Erro ao buscar subcategorias da categoria {categoria_id}: {str(e)}")
            return []

    def gerar_codigos(self, id_produto, prefixo=None):
        """
        Gera códigos pai e filho baseado no ID e prefixo opcional.

        Args:
            id_produto (str): ID do produto
            prefixo (str, optional): Prefixo para os códigos (ex: 'SL')

        Returns:
            tuple: (codigo_pai, codigo_filho)
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

        Args:
            produto (dict): Dicionário com as medidas do produto

        Returns:
            dict: Dicionário com as medidas tratadas
        """
        medidas = {
            'peso': produto.get('peso', 1.000),
            'altura': produto.get('altura', 10),
            'largura': produto.get('largura', 10),
            'comprimento': produto.get('comprimento', 10)
        }

        return {k: limpar_numero(v) for k, v in medidas.items()}

    def cadastrar_produto(self, produto, prefixo=None):
        """
        Cadastra um produto completo (pai e filho) na Magazord.

        Args:
            produto (dict): Dados do produto
            prefixo (str, optional): Prefixo para os códigos

        Returns:
            tuple: (sucesso, resultado)
        """
        try:
            # Gera códigos pai e filho
            codigo_pai, codigo_filho = self.gerar_codigos(produto['id'], prefixo)

            # Trata as medidas
            medidas = self.tratar_medidas(produto)

            # Log das medidas
            logger.info(f"Medidas originais: peso={produto.get('peso')}, altura={produto.get('altura')}, "
                       f"largura={produto.get('largura')}, comprimento={produto.get('comprimento')}")
            logger.info(f"Medidas processadas: {medidas}")

            # Monta o payload do produto pai
            payload_pai = {
                "codigo": codigo_pai,
                "nome": produto['titulo'],
                "marca": int(produto['marca_id']),
                "tipo": 1,  # Produto comum
                "origemFiscal": int(produto.get('origem_fiscal', 0)),
                "unidadeMedida": "UN",
                "peso": medidas['peso'],
                "altura": medidas['altura'],
                "largura": medidas['largura'],
                "comprimento": medidas['comprimento'],
                "ativo": True,
                "dataLancamento": datetime.now().strftime('%Y-%m-%dT00:00:00Z'),
                "categorias": [int(produto['categoria_id'])] if produto.get('categoria_id') else [],
                "derivacoes": [
                    {
                        "id": self.derivacao_id,  # ID 3 para "Único"
                        "codigo": codigo_filho,
                        "nome": produto['titulo'],
                        "peso": medidas['peso'],
                        "altura": medidas['altura'],
                        "largura": medidas['largura'],
                        "comprimento": medidas['comprimento'],
                        "ativo": True,
                        "produtoLoja": [
                            {
                                "loja": self.loja_id,  # ID 1 da loja
                                "ativo": True,
                                "tabelaPreco": self.tabela_preco_id  # ID 1 da tabela de preço
                            }
                        ],
                        "produtoDeposito": [
                            {
                                "deposito": 1,  # ID 1 do depósito
                                "ativo": True
                            }
                        ]
                    }
                ],
                "produtoLoja": [
                    {
                        "loja": self.loja_id,
                        "ativo": True
                    }
                ]
            }

            # Campos opcionais
            campos_opcionais = [
                'descricao', 'caracteristicas', 'especificacoes',
                'ncm', 'cest', 'ean', 'potencia', 'temperatura_cor',
                'tensao', 'ip', 'cor'
            ]

            for campo in campos_opcionais:
                if produto.get(campo):
                    # Mapeia campos com nomes diferentes na API
                    campo_api = {
                        'especificacoes': 'especificacoes_tecnicas',
                        'temperatura_cor': 'temperatura_de_cor'
                    }.get(campo, campo)

                    payload_pai[campo_api] = produto[campo]

            logger.info(f"Cadastrando produto pai {codigo_pai} com filho {codigo_filho}")
            logger.info(f"Payload enviado: {payload_pai}")

            # Cadastra produto pai com filho
            response = self.session.post(f"{base_url}/api/v2/site/produto", json=payload_pai)
            response.raise_for_status()
            resposta_json = response.json()

            # Verifica se o cadastro foi bem sucedido
            if response.status_code in [200, 201]:
                logger.info(f"Produto cadastrado com sucesso! Pai: {codigo_pai}, Filho: {codigo_filho}")
                return True, {
                    'codigo_pai': codigo_pai,
                    'codigo_filho': codigo_filho,
                    'response': resposta_json
                }
            else:
                logger.error(f"Erro ao cadastrar produto. Status: {response.status_code}, Resposta: {resposta_json}")
                return False, f"Erro ao cadastrar produto: {resposta_json}"

        except Exception as e:
            logger.error(f"Erro ao cadastrar produto: {str(e)}")
            return False, str(e)

    def buscar_produto(self, codigo):
        """
        Busca um produto pelo código.

        Args:
            codigo (str): Código do produto

        Returns:
            dict: Dados do produto ou None se não encontrado
        """
        try:
            url = f"{base_url}/api/v2/site/produto/{codigo}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json().get("data")
        except Exception as e:
            logger.error(f"Erro ao buscar produto {codigo}: {str(e)}")
            return None
