# Define os campos obrigatórios e opcionais para o mapeamento do Excel

CAMPOS_OBRIGATORIOS = {
    'id': ['ID', 'Id', 'Código', 'Codigo', 'Cod', 'SKU'],
    'titulo': ['Título', 'Titulo', 'Nome', 'Descrição', 'Descricao', 'DESCRIÇÃO', 'Produto']
}

CAMPOS_OPCIONAIS = {
    'descricao': ['Descrição', 'Descricao', 'Descrição Completa', 'Descricao Completa', 'DESCRIÇÃO COMPLETA'],
    'caracteristicas': ['Características', 'Caracteristicas', 'Característica', 'Caracteristica'],
    'especificacoes': ['Especificações', 'Especificacoes', 'Detalhes', 'Especificação', 'Especificacao'],
    'ncm': ['NCM', 'Ncm', 'NCM_PRODUTO', 'Ncm Produto'],
    'cest': ['CEST', 'Cest', 'CEST_PRODUTO', 'Cest Produto'],
    'peso': ['Peso', 'Peso (kg)', 'Peso KG', 'PESO', 'Peso Bruto', 'Peso Líquido'],
    'altura': ['Altura', 'Altura (cm)', 'ALTURA', 'Alt', 'Alt (cm)'],
    'largura': ['Largura', 'Largura (cm)', 'LARGURA', 'Larg', 'Larg (cm)'],
    'comprimento': ['Comprimento', 'Profundidade', 'Medida', 'COMPRIMENTO', 'Prof', 'Prof (cm)'],
    'ean': ['EAN', 'Ean', 'Código de Barras', 'Codigo de Barras', 'GTIN', 'EAN13'],
    'potencia': ['Potência', 'Potencia', 'POT', 'Watts', 'W'],
    'temperatura_cor': ['Temperatura de Cor', 'Temp Cor', 'Temp. Cor', 'Kelvin', 'K'],
    'tensao': ['Tensão', 'Tensao', 'Voltagem', 'V', 'Volts'],
    'ip': ['IP', 'Ip', 'Índice de Proteção', 'Indice de Protecao'],
    'cor': ['Cor', 'COR', 'Acabamento', 'ACABAMENTO']
}

def mapear_colunas(header):
    """
    Faz o mapeamento das colunas do Excel para os campos obrigatórios e opcionais.

    Args:
        header (list): Lista com os nomes das colunas do arquivo Excel

    Returns:
        tuple: (mapeamento_obrigatorio, mapeamento_opcional)
            - mapeamento_obrigatorio (dict): Dicionário com os campos obrigatórios mapeados
            - mapeamento_opcional (dict): Dicionário com os campos opcionais mapeados

    Example:
        >>> header = ['ID Produto', 'Nome do Produto', 'Peso (kg)', 'NCM']
        >>> obrig, opc = mapear_colunas(header)
        >>> print(obrig)
        {'id': 'ID Produto', 'titulo': 'Nome do Produto'}
        >>> print(opc)
        {'peso': 'Peso (kg)', 'ncm': 'NCM', ...}
    """
    mapeamento_obrigatorio = {}
    mapeamento_opcional = {}

    # Mapeia obrigatórios
    for campo, opcoes in CAMPOS_OBRIGATORIOS.items():
        for opcao in opcoes:
            for col in header:
                if opcao.strip().lower() in str(col).strip().lower():
                    mapeamento_obrigatorio[campo] = col
                    break
            if campo in mapeamento_obrigatorio:
                break

    # Mapeia opcionais
    for campo, opcoes in CAMPOS_OPCIONAIS.items():
        for opcao in opcoes:
            for col in header:
                if opcao.strip().lower() in str(col).strip().lower():
                    mapeamento_opcional[campo] = col
                    break
            if campo in mapeamento_opcional:
                break
        if campo not in mapeamento_opcional:
            mapeamento_opcional[campo] = None

    return mapeamento_obrigatorio, mapeamento_opcional
