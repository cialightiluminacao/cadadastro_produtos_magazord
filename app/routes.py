from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, send_file, jsonify
import os
import pandas as pd
from werkzeug.utils import secure_filename
from app.utils.excel_mapping import mapear_colunas, CAMPOS_OBRIGATORIOS, CAMPOS_OPCIONAIS
from app.utils.magazord_api import MagazordAPI
from app.utils.image_search import get_image_url
from app.utils.scraping import buscar_titulo_inspirehome
import threading
import uuid
import logging
import time
from datetime import datetime
import traceback
from concurrent.futures import ThreadPoolExecutor

# Configuração do logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

main = Blueprint('main', __name__)

# Variáveis globais para controle
progress = {}
produtos_processados = {}
cadastro_status = {}
preview_status = {}
thread_pool = ThreadPoolExecutor(max_workers=3)  # Limita processamento paralelo

# Constantes
ALLOWED_EXTENSIONS = {'xlsx'}
MAX_RETRIES = 3
RETRY_DELAY = 1  # segundos

# Função global para templates
@main.context_processor
def utility_processor():
    return {
        'now': datetime.now,
        'current_year': datetime.now().year
    }

def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_excel_robusto(filepath):
    """Lê arquivo Excel com tratamento de erros robusto"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            df = pd.read_excel(filepath, engine='openpyxl')
            df = df.replace({pd.NA: None})  # Converte NA para None
            return df
        except Exception as e:
            retries += 1
            if retries == MAX_RETRIES:
                logger.error(f'Erro fatal ao abrir arquivo Excel: {e}\n{traceback.format_exc()}')
                raise Exception(f'Erro ao abrir arquivo Excel: {str(e)}')
            logger.warning(f'Tentativa {retries} falhou, tentando novamente em {RETRY_DELAY}s')
            time.sleep(RETRY_DELAY)

def limpar_sessao(user_id):
    """Limpa dados da sessão do usuário"""
    try:
        # Remove arquivos temporários
        for key in ['uploaded_file', 'relatorio_ignorados', 'relatorio_sem_imagem']:
            filepath = session.get(key)
            if filepath and os.path.exists(filepath):
                os.remove(filepath)

        # Limpa variáveis globais
        progress.pop(user_id, None)
        produtos_processados.pop(user_id, None)
        preview_status.pop(user_id, None)
        cadastro_status.pop(user_id, None)

        # Limpa sessão
        session.clear()

    except Exception as e:
        logger.error(f"Erro ao limpar sessão: {e}")

def validar_produto(produto, categorias_magazord):
    """Valida dados do produto antes do cadastro"""
    erros = []

    # Validações básicas
    if not produto.get('id'):
        erros.append("ID do produto é obrigatório")
    if not produto.get('titulo'):
        erros.append("Título do produto é obrigatório")
    if not produto.get('marca_id'):
        erros.append("Marca do produto é obrigatória")

    # Validação de categoria
    if produto.get('categoria_id'):
        categoria_valida = any(
            str(c['id']) == str(produto['categoria_id'])
            for c in categorias_magazord
        )
        if not categoria_valida:
            erros.append("Categoria inválida")

    # Validação de medidas
    for medida in ['peso', 'altura', 'largura', 'comprimento']:
        if produto.get(medida) and not isinstance(produto[medida], (int, float)):
            erros.append(f"{medida.capitalize()} deve ser um número")

    return erros
class ProcessamentoBackground:
    def __init__(self, app, user_id, filepath, mapeamento_obrigatorio, mapeamento_opcional, marca_id, marcas,
                 categorias_magazord, link_fornecedor, prefixo_codigo, origem_fiscal):
        self.app = app
        self.user_id = user_id
        self.filepath = filepath
        self.mapeamento_obrigatorio = mapeamento_obrigatorio
        self.mapeamento_opcional = mapeamento_opcional
        self.marca_id = marca_id
        self.marcas = marcas
        self.categorias_magazord = categorias_magazord
        self.link_fornecedor = link_fornecedor
        self.prefixo_codigo = prefixo_codigo
        self.origem_fiscal = origem_fiscal
        preview_status[self.user_id] = []

    def processar(self):
        logger.info(f"Iniciando processamento em background para user_id: {self.user_id}")
        produtos = []
        ignorados = []
        produtos_sem_imagem = []
        produtos_sem_titulo = []

        with self.app.app_context():
            try:
                logger.info("Lendo arquivo Excel...")
                df = read_excel_robusto(self.filepath)
                df.columns = [str(col).strip() for col in df.columns]
                total = len(df)
                logger.info(f"Total de produtos a processar: {total}")

                for idx, row in df.iterrows():
                    try:
                        logger.info(f"Processando produto {idx+1}/{total}")

                        # Adiciona status inicial
                        status = {
                            "id": str(row.get(self.mapeamento_obrigatorio.get('id', ''), '')),
                            "titulo": str(row.get(self.mapeamento_obrigatorio.get('titulo', ''), '')),
                            "status": "Processando",
                            "mensagem": "Iniciando processamento...",
                            "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                        }
                        preview_status[self.user_id].append(status)

                        # Validação de campos obrigatórios
                        id_ok = self.mapeamento_obrigatorio['id'] in row and pd.notnull(row[self.mapeamento_obrigatorio['id']])
                        titulo_ok = self.mapeamento_obrigatorio['titulo'] in row and pd.notnull(row[self.mapeamento_obrigatorio['titulo']])

                        motivos = []
                        if not id_ok:
                            motivos.append('ID ausente')
                        if not titulo_ok:
                            motivos.append('Título ausente')

                        if motivos:
                            logger.warning(f"Produto ignorado na linha {idx+2}: {', '.join(motivos)}")
                            status["status"] = "ERRO"
                            status["mensagem"] = f"Ignorado: {', '.join(motivos)}"
                            ignorados.append({
                                'linha': idx + 2,
                                'motivo': ', '.join(motivos),
                                'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                                **row.to_dict()
                            })
                            continue

                        produto_id = str(row[self.mapeamento_obrigatorio['id']])
                        marca_nome = next((m['nome'] for m in self.marcas if m['id'] == self.marca_id), "Marca não encontrada")

                        # Atualiza status para busca de título
                        status["mensagem"] = "Buscando título..."

                        # Busca título no fornecedor se link foi informado
                        titulo = None
                        if self.link_fornecedor:
                            logger.info(f"Buscando título para produto {produto_id} no fornecedor...")
                            titulo = buscar_titulo_inspirehome(self.link_fornecedor, produto_id)
                            if not titulo:
                                logger.warning(f"Título não encontrado no fornecedor para produto {produto_id}")
                                produtos_sem_titulo.append({
                                    'id': produto_id,
                                    'titulo_arquivo': row[self.mapeamento_obrigatorio['titulo']],
                                    'data_verificacao': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                                })

                        # Se não encontrou título no fornecedor, usa do arquivo
                        if not titulo:
                            titulo = row[self.mapeamento_obrigatorio['titulo']]

                        # Atualiza status para busca de imagem
                        status["mensagem"] = "Buscando imagem..."

                        # Busca imagem do produto
                        img_url = get_image_url(produto_id, current_app.static_folder)

                        produto = {
                            'id': produto_id,
                            'titulo': titulo,
                            'marca_id': self.marca_id,
                            'marca_nome': marca_nome,
                            'origem_fiscal': self.origem_fiscal,
                            'img_url': img_url,
                            'data_cadastro': datetime.now().strftime('%Y-%m-%d'),
                            'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                        }

                        # Campos opcionais
                        for campo, col in self.mapeamento_opcional.items():
                            if col and col in row and pd.notnull(row[col]):
                                produto[campo] = row[col]

                        # Validação do produto
                        erros_validacao = validar_produto(produto, self.categorias_magazord)
                        if erros_validacao:
                            status["status"] = "ERRO"
                            status["mensagem"] = f"Erros de validação: {', '.join(erros_validacao)}"
                            ignorados.append({
                                'linha': idx + 2,
                                'motivo': ', '.join(erros_validacao),
                                'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                                **row.to_dict()
                            })
                            continue

                        produtos.append(produto)

                        # Se usou imagem em branco, adiciona ao relatório
                        if img_url.endswith("blank_1000x1000.png"):
                            produtos_sem_imagem.append({
                                'id': produto_id,
                                'titulo': titulo,
                                'data_verificacao': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                            })

                        # Atualiza status final do produto
                        status["status"] = "OK"
                        status["mensagem"] = "Processado com sucesso"
                        status["titulo"] = titulo

                        # Atualiza progresso
                        progress[self.user_id] = int((idx + 1) / total * 100)
                        logger.info(f"Progresso: {progress[self.user_id]}%")

                        # Pequena pausa para não sobrecarregar
                        time.sleep(0.1)

                    except Exception as e:
                        logger.error(f"Erro ao processar produto {idx+1}: {e}\n{traceback.format_exc()}")
                        if status:
                            status["status"] = "ERRO"
                            status["mensagem"] = f"Erro: {str(e)}"
                        continue

                # Finaliza processamento
                produtos_processados[self.user_id] = {
                    'produtos': produtos,
                    'ignorados': ignorados,
                    'produtos_sem_imagem': produtos_sem_imagem,
                    'produtos_sem_titulo': produtos_sem_titulo,
                    'data_conclusao': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                }
                progress[self.user_id] = 100
                logger.info("Processamento finalizado com sucesso")

            except Exception as e:
                logger.error(f"Erro fatal no processamento: {e}\n{traceback.format_exc()}")
                progress[self.user_id] = 100
                produtos_processados[self.user_id] = {
                    'erro': str(e),
                    'data_erro': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                }

class CadastroMagazordBackground:
    def __init__(self, app, user_id, produtos, prefixo_codigo):
        self.app = app
        self.user_id = user_id
        self.produtos = produtos
        self.prefixo_codigo = prefixo_codigo
        self.api = MagazordAPI()

    def cadastrar(self):
        total = len(self.produtos)
        cadastro_status[self.user_id] = []

        with self.app.app_context():
            for idx, produto in enumerate(self.produtos):
                status = {
                    "id": produto['id'],
                    "titulo": produto['titulo'],
                    "status": "Processando",
                    "mensagem": "",
                    "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                }

                try:
                    logger.info(f"Cadastrando produto {produto['id']} ({idx+1}/{total})")

                    # Tenta cadastrar com retry
                    retries = 0
                    while retries < MAX_RETRIES:
                        try:
                            ok, resposta = self.api.cadastrar_produto(produto, self.prefixo_codigo)
                            if ok:
                                status["status"] = "OK"
                                status["mensagem"] = f"Cadastrado com sucesso! (Pai: {resposta['codigo_pai']}, Filho: {resposta['codigo_filho']})"
                                logger.info(f"Produto {produto['id']} cadastrado com sucesso")
                                break
                            else:
                                retries += 1
                                if retries == MAX_RETRIES:
                                    status["status"] = "ERRO"
                                    status["mensagem"] = resposta
                                    logger.error(f"Erro ao cadastrar produto {produto['id']}: {resposta}")
                                else:
                                    time.sleep(RETRY_DELAY)
                        except Exception as e:
                            retries += 1
                            if retries == MAX_RETRIES:
                                raise e
                            time.sleep(RETRY_DELAY)

                except Exception as e:
                    status["status"] = "ERRO"
                    status["mensagem"] = str(e)
                    logger.error(f"Exceção ao cadastrar produto {produto['id']}: {e}\n{traceback.format_exc()}")

                cadastro_status[self.user_id].append(status)
                progress[self.user_id] = int((idx + 1) / total * 100)
                time.sleep(0.2)  # Evita sobrecarga na API

            progress[self.user_id] = 100
            logger.info(f"Cadastro finalizado para user_id: {self.user_id}")

@main.route('/', methods=['GET', 'POST'])
def index():
    try:
        api = MagazordAPI()
        marcas = api.get_marcas()

        if request.method == 'POST':
            if 'file' not in request.files or 'marca_id' not in request.form or 'origem_fiscal' not in request.form:
                flash('Arquivo, marca e origem fiscal são obrigatórios!', 'danger')
                return redirect(request.url)

            file = request.files['file']
            marca_id = request.form['marca_id']
            origem_fiscal = request.form['origem_fiscal']
            link_fornecedor = request.form.get('link_fornecedor', '').strip()
            prefixo_codigo = request.form.get('prefixo_codigo', '').strip().upper()

            session['marca_id'] = marca_id
            session['origem_fiscal'] = origem_fiscal
            session['link_fornecedor'] = link_fornecedor
            session['prefixo_codigo'] = prefixo_codigo

            if file.filename == '':
                flash('Nenhum arquivo selecionado!', 'danger')
                return redirect(request.url)

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                session['uploaded_file'] = filepath

                try:
                    df = read_excel_robusto(filepath)
                    df.columns = [str(col).strip() for col in df.columns]
                    header = df.columns
                    mapeamento_obrigatorio, mapeamento_opcional = mapear_colunas(header)
                    session['mapeamento_obrigatorio'] = mapeamento_obrigatorio
                    session['mapeamento_opcional'] = mapeamento_opcional

                    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in mapeamento_obrigatorio]
                    if faltando:
                        flash(f'Os campos obrigatórios {faltando} não foram mapeados. Por favor, revise o mapeamento.', 'danger')
                        return render_template('mapping.html',
                                            header=header,
                                            mapeamento_obrigatorio=mapeamento_obrigatorio,
                                            mapeamento_opcional=mapeamento_opcional,
                                            faltando=faltando)
                    else:
                        return redirect(url_for('main.preview'))

                except Exception as e:
                    logger.error(f"Erro ao processar arquivo: {e}\n{traceback.format_exc()}")
                    flash(str(e), 'danger')
                    return redirect(request.url)
            else:
                flash('Arquivo inválido! Envie apenas arquivos .xlsx.', 'danger')
                return redirect(request.url)

        return render_template('index.html', marcas=marcas)

    except Exception as e:
        logger.error(f"Erro na rota index: {e}\n{traceback.format_exc()}")
        flash("Erro ao carregar a página. Por favor, tente novamente.", 'danger')
        return redirect(url_for('main.index'))

@main.route('/preview', methods=['GET', 'POST'])
def preview():
    try:
        filepath = session.get('uploaded_file')
        mapeamento_obrigatorio = session.get('mapeamento_obrigatorio')
        mapeamento_opcional = session.get('mapeamento_opcional')
        marca_id = int(session.get('marca_id'))
        origem_fiscal = int(session.get('origem_fiscal'))
        marcas = MagazordAPI().get_marcas()
        categorias_magazord = MagazordAPI().get_categorias()
        link_fornecedor = session.get('link_fornecedor', '')
        prefixo_codigo = session.get('prefixo_codigo', '')

        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id

        if user_id not in produtos_processados or 'produtos' not in produtos_processados[user_id]:
            logger.info(f"Iniciando novo processamento para user_id: {user_id}")
            progress[user_id] = 0
            preview_status[user_id] = []

            processador = ProcessamentoBackground(
                current_app._get_current_object(),
                user_id,
                filepath,
                mapeamento_obrigatorio,
                mapeamento_opcional,
                marca_id,
                marcas,
                categorias_magazord,
                link_fornecedor,
                prefixo_codigo,
                origem_fiscal
            )

            thread = threading.Thread(target=processador.processar)
            thread.start()

            return render_template('preview.html',
                                produtos=[],
                                categorias=categorias_magazord,
                                marcas=marcas,
                                relatorio_ignorados=None,
                                relatorio_sem_imagem=None,
                                loading=True)

        resultado = produtos_processados[user_id]

        if 'erro' in resultado:
            flash(f"Erro no processamento: {resultado['erro']}", 'danger')
            return redirect(url_for('main.index'))

        produtos = resultado.get('produtos', [])
        ignorados = resultado.get('ignorados', [])
        produtos_sem_imagem = resultado.get('produtos_sem_imagem', [])
        produtos_sem_titulo = resultado.get('produtos_sem_titulo', [])

        if request.method == 'POST':
            produtos_final = []
            for idx, produto in enumerate(produtos):
                produto_atualizado = produto.copy()
                produto_atualizado['categoria_id'] = request.form.get(f'categoria_id_{idx}')
                produto_atualizado['titulo'] = request.form.get(f'titulo_{idx}')
                produtos_final.append(produto_atualizado)

            session['produtos'] = produtos_final
            progress.pop(user_id, None)
            produtos_processados.pop(user_id, None)
            preview_status.pop(user_id, None)
            return redirect(url_for('main.process'))

        # Gera relatórios se necessário
        relatorio_path = None
        if ignorados:
            relatorio_path = os.path.join(current_app.config['UPLOAD_FOLDER'],
                                        f'relatorio_ignorados_{user_id}.xlsx')
            df_ignorados = pd.DataFrame(ignorados)
            df_ignorados.to_excel(relatorio_path, index=False)
            session['relatorio_ignorados'] = relatorio_path

        relatorio_sem_imagem_path = None
        if produtos_sem_imagem:
            relatorio_sem_imagem_path = os.path.join(current_app.config['UPLOAD_FOLDER'],
                                        f'relatorio_sem_imagem_{user_id}.xlsx')
            df_sem_imagem = pd.DataFrame(produtos_sem_imagem)
            df_sem_imagem.to_excel(relatorio_sem_imagem_path, index=False)
            session['relatorio_sem_imagem'] = relatorio_sem_imagem_path

        return render_template('preview.html',
                            produtos=produtos,
                            categorias=categorias_magazord,
                            marcas=marcas,
                            relatorio_ignorados=relatorio_path,
                            relatorio_sem_imagem=relatorio_sem_imagem_path,
                            loading=False)

    except Exception as e:
        logger.error(f"Erro na rota preview: {e}\n{traceback.format_exc()}")
        flash("Erro ao processar preview. Por favor, tente novamente.", 'danger')
        return redirect(url_for('main.index'))

@main.route('/process', methods=['GET', 'POST'])
def process():
    try:
        produtos = session.get('produtos', [])
        prefixo_codigo = session.get('prefixo_codigo', '')
        user_id = session.get('user_id')

        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id

        if user_id not in cadastro_status or not cadastro_status[user_id]:
            progress[user_id] = 0
            cadastro_status[user_id] = []

            cadastro_thread = CadastroMagazordBackground(
                current_app._get_current_object(),
                user_id,
                produtos,
                prefixo_codigo
            )

            thread = threading.Thread(target=cadastro_thread.cadastrar)
            thread.start()

            return render_template('process.html',
                                resultados=[],
                                loading=True)

        resultados = cadastro_status[user_id]
        loading = progress.get(user_id, 0) < 100

        if not loading:
            # Limpa a sessão quando finalizar
            limpar_sessao(user_id)

        return render_template('process.html',
                            resultados=resultados,
                            loading=loading)

    except Exception as e:
        logger.error(f"Erro na rota process: {e}\n{traceback.format_exc()}")
        flash("Erro ao processar produtos. Por favor, tente novamente.", 'danger')
        return redirect(url_for('main.index'))

@main.route('/progress')
def get_progress():
    try:
        user_id = session.get('user_id')
        return jsonify({'progress': progress.get(user_id, 0)})
    except Exception as e:
        logger.error(f"Erro ao buscar progresso: {e}")
        return jsonify({'progress': 0})

@main.route('/preview_status')
def get_preview_status():
    try:
        user_id = session.get('user_id')
        return jsonify({'status': preview_status.get(user_id, [])})
    except Exception as e:
        logger.error(f"Erro ao buscar status do preview: {e}")
        return jsonify({'status': []})

@main.route('/cadastro_status')
def get_cadastro_status():
    try:
        user_id = session.get('user_id')
        return jsonify({'status': cadastro_status.get(user_id, [])})
    except Exception as e:
        logger.error(f"Erro ao buscar status do cadastro: {e}")
        return jsonify({'status': []})

@main.route('/relatorio-ignorados')
def relatorio_ignorados():
    try:
        relatorio_path = session.get('relatorio_ignorados')
        if relatorio_path and os.path.exists(relatorio_path):
            return send_file(relatorio_path,
                            as_attachment=True,
                            download_name='relatorio_produtos_ignorados.xlsx')
        flash('Relatório não encontrado.', 'danger')
        return redirect(url_for('main.preview'))
    except Exception as e:
        logger.error(f"Erro ao baixar relatório de ignorados: {e}")
        flash('Erro ao gerar relatório.', 'danger')
        return redirect(url_for('main.preview'))

@main.route('/relatorio-sem-imagem')
def relatorio_sem_imagem():
    try:
        relatorio_path = session.get('relatorio_sem_imagem')
        if relatorio_path and os.path.exists(relatorio_path):
            return send_file(relatorio_path,
                            as_attachment=True,
                            download_name='relatorio_produtos_sem_imagem.xlsx')
        flash('Relatório não encontrado.', 'danger')
        return redirect(url_for('main.preview'))
    except Exception as e:
        logger.error(f"Erro ao baixar relatório de produtos sem imagem: {e}")
        flash('Erro ao gerar relatório.', 'danger')
        return redirect(url_for('main.preview'))
