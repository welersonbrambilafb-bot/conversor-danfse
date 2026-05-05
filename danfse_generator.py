# -*- coding: utf-8 -*-
"""
=============================================================================
  GERADOR DE DANFSe - Documento Auxiliar da NFS-e Padrão Nacional (v1.0)
=============================================================================
  Lê um XML da NFS-e no Padrão Nacional (leiaute oficial CGNFS-e)
  e gera um PDF da DANFSe compatível com o modelo oficial.

  Uso:
     1) Execute o script (python danfse_generator.py)
     2) Selecione o arquivo XML da NFS-e
     3) Selecione a pasta de destino do PDF
     4) O PDF é gerado com o nome baseado na chave de acesso

  Compatível com XML versão 1.00 / 1.01 (NT 004 / NT 007)
=============================================================================
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO

# tkinter é importado apenas quando necessário (modo GUI).
# Isso permite que o modo CLI funcione em ambientes sem tkinter instalado
# (ex.: servidores Linux, subprocess chamado pelo dms_tomados.py).

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image as RLImage, KeepTogether, PageBreak
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =============================================================================
# NAMESPACES / CONSTANTES
# =============================================================================
NS = {'nfse': 'http://www.sped.fazenda.gov.br/nfse'}

# URL do portal nacional para consulta da NFS-e
URL_CONSULTA = "https://www.nfse.gov.br/EmissorNacional/ConsultarNFSe"


# =============================================================================
# FUNÇÕES UTILITÁRIAS DE PARSE
# =============================================================================
def strip_ns(tag):
    """Remove namespace de uma tag XML."""
    return re.sub(r'\{.*\}', '', tag)


def _f(el, path, default=""):
    """Busca texto em um elemento XML considerando o namespace."""
    if el is None:
        return default
    found = el.find(path, NS)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _el(el, path):
    """Retorna um elemento XML (ou None)."""
    if el is None:
        return None
    return el.find(path, NS)


def _all(el, path):
    """Retorna lista de elementos que casam com o path."""
    if el is None:
        return []
    return el.findall(path, NS)


# =============================================================================
# FUNÇÕES DE FORMATAÇÃO
# =============================================================================
def fmt_moeda(valor):
    """Formata valor float para formato BR (1.234,56)."""
    try:
        v = float(valor)
    except (ValueError, TypeError):
        return "-"
    s = f"{v:,.2f}"
    # Troca separadores para formato brasileiro
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _eh_retencao(valor):
    """Retorna True se a string `valor` representa um número estritamente > 0,
    ou seja, indica que há efetivamente uma retenção a ser destacada.
    """
    if valor is None:
        return False
    s = str(valor).strip()
    if not s or s == '-':
        return False
    try:
        return float(s) > 0
    except (ValueError, TypeError):
        return False


def fmt_num(valor, casas=2):
    """Formata número simples em padrão BR."""
    try:
        v = float(valor)
    except (ValueError, TypeError):
        return "-"
    s = f"{v:,.{casas}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def fmt_perc(valor):
    """Formata porcentagem."""
    try:
        v = float(valor)
    except (ValueError, TypeError):
        return "-"
    s = f"{v:.2f}".replace(".", ",")
    return f"{s}%"


def fmt_cnpj_cpf(doc):
    """Formata CNPJ ou CPF."""
    if not doc:
        return "-"
    doc = re.sub(r'\D', '', doc)
    if len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:14]}"
    elif len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:11]}"
    return doc


def fmt_cep(cep):
    """Formata CEP."""
    if not cep:
        return "-"
    cep = re.sub(r'\D', '', cep)
    if len(cep) == 8:
        return f"{cep[:5]}-{cep[5:]}"
    return cep


def fmt_fone(fone):
    """Formata telefone."""
    if not fone:
        return "-"
    fone = re.sub(r'\D', '', fone)
    if len(fone) == 11:
        return f"({fone[:2]}) {fone[2:7]}-{fone[7:]}"
    if len(fone) == 10:
        return f"({fone[:2]}) {fone[2:6]}-{fone[6:]}"
    return fone


def fmt_codtrib(codigo):
    """Formata código de tributação nacional (ex.: 010701 -> 01.07.01)."""
    if not codigo:
        return "-"
    codigo = codigo.strip()
    if len(codigo) == 6 and codigo.isdigit():
        return f"{codigo[:2]}.{codigo[2:4]}.{codigo[4:6]}"
    return codigo


def fmt_data(data_iso):
    """Converte string ISO em dd/mm/aaaa."""
    if not data_iso:
        return "-"
    try:
        # Tenta formato com timezone
        try:
            dt = datetime.fromisoformat(data_iso)
        except ValueError:
            # fallback sem timezone
            dt = datetime.strptime(data_iso[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return data_iso


def fmt_datahora(data_iso):
    """Converte string ISO em dd/mm/aaaa HH:MM:SS."""
    if not data_iso:
        return "-"
    try:
        try:
            dt = datetime.fromisoformat(data_iso)
        except ValueError:
            dt = datetime.strptime(data_iso[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return data_iso


def fmt_cep_endereco(end_dict):
    """Retorna endereço formatado."""
    parts = []
    if end_dict.get('xLgr'):
        parts.append(end_dict['xLgr'])
    if end_dict.get('nro'):
        parts.append(end_dict['nro'])
    if end_dict.get('xCpl'):
        parts.append(end_dict['xCpl'])
    if end_dict.get('xBairro'):
        parts.append(end_dict['xBairro'])
    return ", ".join([p for p in parts if p])


# =============================================================================
# TABELA DE CÓDIGOS IBGE
# =============================================================================
# Mapeamento `codigo_ibge (7 dígitos) -> (nome, uf)` para todos os municípios
# brasileiros. A tabela é carregada de uma das seguintes fontes, em ordem de
# prioridade:
#
#   1. Arquivo JSON `municipios_ibge.json` na mesma pasta do script
#      (formato: {"4105508": {"nome": "Cianorte", "uf": "PR"}, ...})
#
#   2. Biblioteca `pyUFbr` (se instalada):  pip install pyUFbr
#      Tem cerca de 5.291 municípios embutidos.
#
#   3. API oficial do IBGE (primeira execução — requer internet):
#      https://servicodados.ibge.gov.br/api/v1/localidades/municipios
#      Após baixar, o arquivo é salvo como `municipios_ibge.json` para uso
#      offline nas próximas execuções.
#
#   4. Fallback reduzido (capitais + municípios de exemplo) embutido no script.
#
# Mínimo de fallback — usado apenas se tudo acima falhar.
MUNICIPIOS_FALLBACK = {
    "1100205": ("Porto Velho", "RO"),     "1200401": ("Rio Branco", "AC"),
    "1302603": ("Manaus", "AM"),          "1400100": ("Boa Vista", "RR"),
    "1501402": ("Belém", "PA"),           "1600303": ("Macapá", "AP"),
    "1721000": ("Palmas", "TO"),          "2111300": ("São Luís", "MA"),
    "2211001": ("Teresina", "PI"),        "2304400": ("Fortaleza", "CE"),
    "2408102": ("Natal", "RN"),           "2507507": ("João Pessoa", "PB"),
    "2611606": ("Recife", "PE"),          "2704302": ("Maceió", "AL"),
    "2800308": ("Aracaju", "SE"),         "2927408": ("Salvador", "BA"),
    "3106200": ("Belo Horizonte", "MG"),  "3205309": ("Vitória", "ES"),
    "3304557": ("Rio de Janeiro", "RJ"),  "3550308": ("São Paulo", "SP"),
    "4106902": ("Curitiba", "PR"),        "4205407": ("Florianópolis", "SC"),
    "4314902": ("Porto Alegre", "RS"),    "5002704": ("Campo Grande", "MS"),
    "5103403": ("Cuiabá", "MT"),          "5208707": ("Goiânia", "GO"),
    "5300108": ("Brasília", "DF"),
    # Municípios dos XMLs de exemplo
    "3505708": ("Barueri", "SP"),         "4105508": ("Cianorte", "PR"),
    "4218004": ("Tijucas", "SC"),
}

# Cache em memória da base de municípios (lazy-load)
_MUNICIPIOS_CACHE = None


def _caminho_json_municipios():
    """Retorna o caminho do arquivo municipios_ibge.json ao lado do script."""
    try:
        pasta = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pasta = os.getcwd()
    return os.path.join(pasta, 'municipios_ibge.json')


def _carregar_de_json_local():
    """Tenta carregar o arquivo municipios_ibge.json ao lado do script."""
    import json
    caminho = _caminho_json_municipios()
    if not os.path.isfile(caminho):
        return None
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        # Normaliza formato: {codigo: {nome, uf}} ou {codigo: [nome, uf]}
        mapa = {}
        for cod, val in dados.items():
            cod_str = str(cod).zfill(7)
            if isinstance(val, dict):
                mapa[cod_str] = (val.get('nome', cod_str), val.get('uf', ''))
            elif isinstance(val, (list, tuple)) and len(val) >= 2:
                mapa[cod_str] = (val[0], val[1])
        return mapa if mapa else None
    except Exception:
        return None


def _carregar_de_pyufbr():
    """Tenta carregar usando a biblioteca pyUFbr (se instalada)."""
    try:
        from pyUFbr.baseuf import ufbr  # type: ignore
    except Exception:
        return None
    try:
        mapa = {}
        for uf in ufbr.list_uf:
            for nome_cidade in ufbr.list_cidades(uf):
                info = ufbr.get_cidade(nome_cidade)
                cod = str(info.codigo).split('.')[0].zfill(7)
                mapa[cod] = (info.nome.title(), uf)
        return mapa if mapa else None
    except Exception:
        return None


def _baixar_da_api_ibge():
    """
    Tenta baixar a lista de municípios da API oficial do IBGE.
    Requer conexão à internet. Salva o resultado em municipios_ibge.json.
    """
    try:
        import json
        try:
            import urllib.request as ur
        except ImportError:
            return None

        url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
        req = ur.Request(url, headers={'User-Agent': 'danfse-generator/1.0'})
        # timeout curto para não travar a primeira execução
        with ur.urlopen(req, timeout=15) as resp:
            dados = json.loads(resp.read().decode('utf-8'))

        mapa = {}
        for m in dados:
            cod = str(m.get('id', '')).zfill(7)
            nome = m.get('nome', cod)
            # caminho hierárquico: microrregiao > mesorregiao > UF > sigla
            uf = ''
            try:
                uf = m['microrregiao']['mesorregiao']['UF']['sigla']
            except (KeyError, TypeError):
                pass
            mapa[cod] = (nome, uf)

        # Persiste em disco como cache para próximas execuções
        try:
            # Formato compacto: {"4105508": {"nome": "Cianorte", "uf": "PR"}}
            serializavel = {k: {'nome': v[0], 'uf': v[1]} for k, v in mapa.items()}
            with open(_caminho_json_municipios(), 'w', encoding='utf-8') as f:
                json.dump(serializavel, f, ensure_ascii=False, separators=(',', ':'))
        except Exception:
            pass  # sem permissão de escrita, segue em memória

        return mapa if mapa else None
    except Exception:
        return None


def obter_municipios():
    """
    Carrega a base de municípios uma única vez (cache em memória).
    Ordem de prioridade: arquivo JSON local → pyUFbr → API IBGE → fallback.
    """
    global _MUNICIPIOS_CACHE
    if _MUNICIPIOS_CACHE is not None:
        return _MUNICIPIOS_CACHE

    for fonte in (_carregar_de_json_local,
                  _carregar_de_pyufbr,
                  _baixar_da_api_ibge):
        resultado = fonte()
        if resultado and len(resultado) > 100:
            # Completa com fallback para eventuais códigos faltantes
            for cod, val in MUNICIPIOS_FALLBACK.items():
                resultado.setdefault(cod, val)
            _MUNICIPIOS_CACHE = resultado
            return _MUNICIPIOS_CACHE

    # Último recurso: fallback mínimo (capitais)
    _MUNICIPIOS_CACHE = dict(MUNICIPIOS_FALLBACK)
    return _MUNICIPIOS_CACHE


def municipio_por_ibge(codigo):
    """
    Retorna (nome, uf) do município pelo código IBGE (7 dígitos).
    Se não encontrar, retorna (codigo, '').
    """
    if not codigo:
        return ("-", "")
    cod = str(codigo).strip().zfill(7)
    base = obter_municipios()
    return base.get(cod, (cod, ""))


# =============================================================================
# PARSER DO XML DA NFS-e
# =============================================================================
def parse_nfse(xml_path):
    """Parseia o XML da NFS-e e retorna dicionário estruturado."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Detecta se existe namespace; se não, força consulta sem NS
    global NS
    if '}' in root.tag:
        uri = root.tag.split('}')[0].strip('{')
        NS = {'nfse': uri}
    else:
        NS = {}

    # Wrappers para busca com/sem namespace
    def fx(el, p, d=""):
        if el is None:
            return d
        # Se não há namespace, remove prefixos "nfse:"
        if not NS:
            p = p.replace('nfse:', '')
        r = el.find(p, NS) if NS else el.find(p)
        return r.text.strip() if (r is not None and r.text) else d

    def ex(el, p):
        if el is None:
            return None
        if not NS:
            p = p.replace('nfse:', '')
        return el.find(p, NS) if NS else el.find(p)

    # ---- Raiz NFSe / infNFSe ----
    inf = ex(root, 'nfse:infNFSe')
    if inf is None:
        raise ValueError("XML inválido: não contém infNFSe")

    chave_acesso = inf.get('Id', '').replace('NFS', '')

    data = {
        'versao': root.get('versao', '1.00'),
        'chave_acesso': chave_acesso,
        # --- Dados gerais da NFSe
        'xLocEmi': fx(inf, 'nfse:xLocEmi'),
        'xLocPrestacao': fx(inf, 'nfse:xLocPrestacao'),
        'nNFSe': fx(inf, 'nfse:nNFSe'),
        'cLocIncid': fx(inf, 'nfse:cLocIncid'),
        'xLocIncid': fx(inf, 'nfse:xLocIncid'),
        'xTribNac': fx(inf, 'nfse:xTribNac'),
        'xTribMun': fx(inf, 'nfse:xTribMun'),
        'xNBS': fx(inf, 'nfse:xNBS'),
        'verAplic': fx(inf, 'nfse:verAplic'),
        'ambGer': fx(inf, 'nfse:ambGer'),
        'tpEmis': fx(inf, 'nfse:tpEmis'),
        'cStat': fx(inf, 'nfse:cStat'),
        'dhProc': fx(inf, 'nfse:dhProc'),
        'nDFSe': fx(inf, 'nfse:nDFSe'),
    }

    # --- Emitente ---
    emit = ex(inf, 'nfse:emit')
    emit_end = ex(emit, 'nfse:enderNac') if emit is not None else None
    data['emit'] = {
        'CNPJ': fx(emit, 'nfse:CNPJ'),
        'CPF': fx(emit, 'nfse:CPF'),
        'NIF': fx(emit, 'nfse:NIF'),
        'IM': fx(emit, 'nfse:IM'),
        'xNome': fx(emit, 'nfse:xNome'),
        'fone': fx(emit, 'nfse:fone'),
        'email': fx(emit, 'nfse:email'),
        'xLgr': fx(emit_end, 'nfse:xLgr'),
        'nro': fx(emit_end, 'nfse:nro'),
        'xCpl': fx(emit_end, 'nfse:xCpl'),
        'xBairro': fx(emit_end, 'nfse:xBairro'),
        'cMun': fx(emit_end, 'nfse:cMun'),
        'UF': fx(emit_end, 'nfse:UF'),
        'CEP': fx(emit_end, 'nfse:CEP'),
    }

    # --- Valores da NFS-e ---
    val = ex(inf, 'nfse:valores')
    data['valores_nfse'] = {
        'vBC': fx(val, 'nfse:vBC'),
        'pAliqAplic': fx(val, 'nfse:pAliqAplic'),
        'vISSQN': fx(val, 'nfse:vISSQN'),
        'vTotalRet': fx(val, 'nfse:vTotalRet'),
        'vLiq': fx(val, 'nfse:vLiq'),
    }

    # --- IBS/CBS no nível NFSe ---
    ibscbs_nfse = ex(inf, 'nfse:IBSCBS')
    if ibscbs_nfse is not None:
        tot = ex(ibscbs_nfse, 'nfse:totCIBS')
        val_ibs = ex(ibscbs_nfse, 'nfse:valores')
        data['ibscbs_nfse'] = {
            'cLocalidadeIncid': fx(ibscbs_nfse, 'nfse:cLocalidadeIncid'),
            'xLocalidadeIncid': fx(ibscbs_nfse, 'nfse:xLocalidadeIncid'),
            'vBC': fx(val_ibs, 'nfse:vBC') if val_ibs is not None else '',
            'pIBSUF': fx(val_ibs, 'nfse:uf/nfse:pIBSUF') if val_ibs is not None else '',
            'pIBSMun': fx(val_ibs, 'nfse:mun/nfse:pIBSMun') if val_ibs is not None else '',
            'pCBS': fx(val_ibs, 'nfse:fed/nfse:pCBS') if val_ibs is not None else '',
            'vTotNF': fx(tot, 'nfse:vTotNF') if tot is not None else '',
            'vIBSTot': fx(tot, 'nfse:gIBS/nfse:vIBSTot') if tot is not None else '',
            'vIBSUF': fx(tot, 'nfse:gIBS/nfse:gIBSUFTot/nfse:vIBSUF') if tot is not None else '',
            'vIBSMun': fx(tot, 'nfse:gIBS/nfse:gIBSMunTot/nfse:vIBSMun') if tot is not None else '',
            'vCBS': fx(tot, 'nfse:gCBS/nfse:vCBS') if tot is not None else '',
        }
    else:
        data['ibscbs_nfse'] = None

    # --- DPS / infDPS ---
    dps = ex(inf, 'nfse:DPS')
    infdps = ex(dps, 'nfse:infDPS') if dps is not None else None

    data['dps'] = {
        'versao': dps.get('versao', '') if dps is not None else '',
        'tpAmb': fx(infdps, 'nfse:tpAmb'),
        'dhEmi': fx(infdps, 'nfse:dhEmi'),
        'verAplic': fx(infdps, 'nfse:verAplic'),
        'serie': fx(infdps, 'nfse:serie'),
        'nDPS': fx(infdps, 'nfse:nDPS'),
        'dCompet': fx(infdps, 'nfse:dCompet'),
        'tpEmit': fx(infdps, 'nfse:tpEmit'),
        'cLocEmi': fx(infdps, 'nfse:cLocEmi'),
    }

    # --- Prestador (dentro de DPS) ---
    prest = ex(infdps, 'nfse:prest') if infdps is not None else None
    regTrib = ex(prest, 'nfse:regTrib') if prest is not None else None
    data['prest'] = {
        'CNPJ': fx(prest, 'nfse:CNPJ'),
        'CPF': fx(prest, 'nfse:CPF'),
        'NIF': fx(prest, 'nfse:NIF'),
        'IM': fx(prest, 'nfse:IM'),
        'fone': fx(prest, 'nfse:fone'),
        'email': fx(prest, 'nfse:email'),
        'opSimpNac': fx(regTrib, 'nfse:opSimpNac'),
        'regApTribSN': fx(regTrib, 'nfse:regApTribSN'),
        'regEspTrib': fx(regTrib, 'nfse:regEspTrib'),
    }

    # --- Tomador ---
    toma = ex(infdps, 'nfse:toma') if infdps is not None else None
    if toma is not None:
        toma_end = ex(toma, 'nfse:end')
        toma_endnac = ex(toma_end, 'nfse:endNac') if toma_end is not None else None
        toma_endext = ex(toma_end, 'nfse:endExt') if toma_end is not None else None
        data['toma'] = {
            'identificado': True,
            'CNPJ': fx(toma, 'nfse:CNPJ'),
            'CPF': fx(toma, 'nfse:CPF'),
            'NIF': fx(toma, 'nfse:NIF'),
            'IM': fx(toma, 'nfse:IM'),
            'xNome': fx(toma, 'nfse:xNome'),
            'fone': fx(toma, 'nfse:fone'),
            'email': fx(toma, 'nfse:email'),
            'xLgr': fx(toma_end, 'nfse:xLgr'),
            'nro': fx(toma_end, 'nfse:nro'),
            'xCpl': fx(toma_end, 'nfse:xCpl'),
            'xBairro': fx(toma_end, 'nfse:xBairro'),
            'cMun': fx(toma_endnac, 'nfse:cMun'),
            'CEP': fx(toma_endnac, 'nfse:CEP'),
            'UF': fx(toma_endnac, 'nfse:UF'),
            'exterior': toma_endext is not None,
        }
    else:
        data['toma'] = {'identificado': False}

    # --- Intermediário ---
    interm = ex(infdps, 'nfse:interm') if infdps is not None else None
    if interm is not None:
        interm_end = ex(interm, 'nfse:end')
        interm_endnac = ex(interm_end, 'nfse:endNac') if interm_end is not None else None
        interm_endext = ex(interm_end, 'nfse:endExt') if interm_end is not None else None
        data['interm'] = {
            'identificado': True,
            'CNPJ': fx(interm, 'nfse:CNPJ'),
            'CPF': fx(interm, 'nfse:CPF'),
            'NIF': fx(interm, 'nfse:NIF'),
            'IM': fx(interm, 'nfse:IM'),
            'xNome': fx(interm, 'nfse:xNome'),
            'fone': fx(interm, 'nfse:fone'),
            'email': fx(interm, 'nfse:email'),
            # Endereço (mesma estrutura do tomador)
            'xLgr': fx(interm_end, 'nfse:xLgr'),
            'nro': fx(interm_end, 'nfse:nro'),
            'xCpl': fx(interm_end, 'nfse:xCpl'),
            'xBairro': fx(interm_end, 'nfse:xBairro'),
            'cMun': fx(interm_endnac, 'nfse:cMun'),
            'CEP': fx(interm_endnac, 'nfse:CEP'),
            'UF': fx(interm_endnac, 'nfse:UF'),
            'exterior': interm_endext is not None,
        }
    else:
        data['interm'] = {'identificado': False}

    # --- Serviço ---
    serv = ex(infdps, 'nfse:serv') if infdps is not None else None
    locPrest = ex(serv, 'nfse:locPrest') if serv is not None else None
    cServ = ex(serv, 'nfse:cServ') if serv is not None else None
    infoCompl = ex(serv, 'nfse:infoCompl') if serv is not None else None

    data['serv'] = {
        'cLocPrestacao': fx(locPrest, 'nfse:cLocPrestacao'),
        'cPaisPrestacao': fx(locPrest, 'nfse:cPaisPrestacao'),
        'cTribNac': fx(cServ, 'nfse:cTribNac'),
        'cTribMun': fx(cServ, 'nfse:cTribMun'),
        'xDescServ': fx(cServ, 'nfse:xDescServ'),
        'cNBS': fx(cServ, 'nfse:cNBS'),
        'xInfComp': fx(infoCompl, 'nfse:xInfComp'),
    }

    # --- Valores da DPS ---
    vals_dps = ex(infdps, 'nfse:valores') if infdps is not None else None
    v_serv = ex(vals_dps, 'nfse:vServPrest') if vals_dps is not None else None
    v_desc = ex(vals_dps, 'nfse:vDescCondIncond') if vals_dps is not None else None
    v_ded = ex(vals_dps, 'nfse:vDedRed') if vals_dps is not None else None
    trib = ex(vals_dps, 'nfse:trib') if vals_dps is not None else None
    tribMun = ex(trib, 'nfse:tribMun') if trib is not None else None
    tribFed = ex(trib, 'nfse:tribFed') if trib is not None else None
    piscofins = ex(tribFed, 'nfse:piscofins') if tribFed is not None else None
    totTrib = ex(trib, 'nfse:totTrib') if trib is not None else None
    vTotTrib = ex(totTrib, 'nfse:vTotTrib') if totTrib is not None else None
    pTotTrib = ex(totTrib, 'nfse:pTotTrib') if totTrib is not None else None
    # Grupo de suspensão da exigibilidade (leiaute oficial v1.00.02)
    exigSusp = ex(tribMun, 'nfse:exigSusp') if tribMun is not None else None
    # Grupo de benefício municipal (leiaute oficial v1.00.02)
    bm = ex(tribMun, 'nfse:BM') if tribMun is not None else None

    data['valores_dps'] = {
        'vServ': fx(v_serv, 'nfse:vServ'),
        'vRecebido': fx(v_serv, 'nfse:vRecebido'),
        'vDescIncond': fx(v_desc, 'nfse:vDescIncond'),
        'vDescCond': fx(v_desc, 'nfse:vDescCond'),
        'vDR': fx(v_ded, 'nfse:vDR'),
        # Tributação municipal
        'tribISSQN': fx(tribMun, 'nfse:tribISSQN'),
        'tpRetISSQN': fx(tribMun, 'nfse:tpRetISSQN'),
        'pAliq': fx(tribMun, 'nfse:pAliq'),
        'tpImunidade': fx(tribMun, 'nfse:tpImunidade'),
        'vISSQN_trib': fx(tribMun, 'nfse:vISSQN'),
        'cPaisResult': fx(tribMun, 'nfse:cPaisResult'),
        # Suspensão da exigibilidade (estrutura oficial)
        'tpSusp': fx(exigSusp, 'nfse:tpSusp'),
        'nProcesso': fx(exigSusp, 'nfse:nProcesso'),
        # Compat: campos antigos mantidos para não quebrar leituras anteriores
        'exigISSQN': fx(tribMun, 'nfse:exigISSQN'),
        'nProcSusp': fx(tribMun, 'nfse:nProcSusp'),
        # Benefício Municipal (BM)
        'nBM': fx(bm, 'nfse:nBM'),
        'vRedBCBM': fx(bm, 'nfse:vRedBCBM'),
        'pRedBCBM': fx(bm, 'nfse:pRedBCBM'),
        # Compat: campos antigos de BM
        'tpBM': fx(tribMun, 'nfse:tpBM'),
        'tpBenef': fx(tribMun, 'nfse:tpBenef'),
        # PIS/COFINS
        'CST_piscofins': fx(piscofins, 'nfse:CST'),
        'vBCPisCofins': fx(piscofins, 'nfse:vBCPisCofins'),
        'pAliqPis': fx(piscofins, 'nfse:pAliqPis'),
        'pAliqCofins': fx(piscofins, 'nfse:pAliqCofins'),
        'vPis': fx(piscofins, 'nfse:vPis'),
        'vCofins': fx(piscofins, 'nfse:vCofins'),
        'tpRetPisCofins': fx(piscofins, 'nfse:tpRetPisCofins'),
        # Outras retenções federais
        'vRetCP': fx(tribFed, 'nfse:vRetCP'),
        'vRetIRRF': fx(tribFed, 'nfse:vRetIRRF'),
        'vRetCSLL': fx(tribFed, 'nfse:vRetCSLL'),
        # Totais aproximados - VALORES (R$) - grupo vTotTrib
        'vTotTribFed': fx(vTotTrib, 'nfse:vTotTribFed'),
        'vTotTribEst': fx(vTotTrib, 'nfse:vTotTribEst'),
        'vTotTribMun': fx(vTotTrib, 'nfse:vTotTribMun'),
        # Totais aproximados - PERCENTUAIS (%) - grupo pTotTrib (Lucro Real/Presumido)
        'pTotTribFed': fx(pTotTrib, 'nfse:pTotTribFed'),
        'pTotTribEst': fx(pTotTrib, 'nfse:pTotTribEst'),
        'pTotTribMun': fx(pTotTrib, 'nfse:pTotTribMun'),
        # Percentual total (Simples Nacional)
        'pTotTribSN': fx(totTrib, 'nfse:pTotTribSN'),
        'indTotTrib': fx(totTrib, 'nfse:indTotTrib'),
    }

    # --- IBS/CBS dentro da DPS ---
    ibscbs_dps = ex(infdps, 'nfse:IBSCBS') if infdps is not None else None
    if ibscbs_dps is not None:
        data['ibscbs_dps'] = {
            'finNFSe': fx(ibscbs_dps, 'nfse:finNFSe'),
            'cIndOp': fx(ibscbs_dps, 'nfse:cIndOp'),
            'indDest': fx(ibscbs_dps, 'nfse:indDest'),
        }
    else:
        data['ibscbs_dps'] = None

    return data


# =============================================================================
# TRADUÇÕES DE CÓDIGOS (dicionários)
# =============================================================================
TRIBISSQN_DESC = {
    '1': 'Operação Tributável',
    '2': 'Operação Imune',
    '3': 'Operação de Exportação',
    '4': 'Operação Não Incidente',
}

TPRETISSQN_DESC = {
    '1': 'Não Retido',
    '2': 'Retido pelo Tomador',
    '3': 'Retido pelo Intermediário',
}

REGESP_DESC = {
    '0': 'Nenhum',
    '1': 'Ato Cooperado (Cooperativa)',
    '2': 'Estimativa',
    '3': 'Microempresa Municipal',
    '4': 'Notário ou Registrador',
    '5': 'Profissional Autônomo',
    '6': 'Sociedade de Profissionais',
}

# Conforme leiaute oficial v1.00.02 - Anexo IV (SE/CGNFS-e)
# Atenção: os códigos 2 (MEI) e 3 (ME/EPP) são fonte comum de confusão -
# aqui está conforme o Anexo IV oficial publicado pelo Comitê Gestor.
OPSIMPNAC_DESC = {
    '1': 'Não Optante',
    '2': 'Optante - Microempreendedor Individual (MEI)',
    '3': 'Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)',
}

# Regime de Apuração Tributária pelo SN (só para ME/EPP - opSimpNac=3)
REGAPTRIBSN_DESC = {
    '1': 'Tributos federais e municipal pelo SN',
    '2': 'Tributos federais pelo SN; ISSQN pela legislação municipal',
    '3': 'Tributos federais e municipal pela NFS-e conforme legislações',
}

# Conforme leiaute oficial v1.00.02: tpRetPisCofins tem apenas 1 e 2.
# Códigos 0, 3 e 4 aparecem em XMLs reais emitidos antes da NT007 — mantemos
# descrições compatíveis para não exibir "Não especificado".
TPRETPISCOFINS_DESC = {
    '0': 'Não se aplica',
    '1': 'Retido',
    '2': 'Não Retido',
    '3': 'PIS/COFINS/CSLL Retidos (NT anterior)',
    '4': 'Apenas COFINS Retido (NT anterior)',
}

CST_PISCOFINS_DESC = {
    '00': 'Nenhum',
    '01': 'Operação Tributável com Alíquota Básica',
    '02': 'Operação Tributável com Alíquota Diferenciada',
    '03': 'Operação Tributável com Alíquota por Unidade de Medida',
    '04': 'Operação Tributável monofásica - Revenda Alíquota Zero',
    '05': 'Operação Tributável por Substituição Tributária',
    '06': 'Operação Tributável a Alíquota Zero',
    '07': 'Operação Tributável da Contribuição',
    '08': 'Operação sem Incidência da Contribuição',
    '09': 'Operação com Suspensão da Contribuição',
}


# =============================================================================
# GERAÇÃO DO QR CODE
# =============================================================================
def gerar_qrcode(chave):
    """Gera QRCode com link de consulta da NFS-e."""
    url = f"{URL_CONSULTA}?chaveAcesso={chave}"
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# =============================================================================
# MONTAGEM DO PDF (DANFSe)
# =============================================================================
# Paleta / estilos base
COR_TITULO_FAIXA = colors.HexColor('#e5e5e5')
COR_LABEL = colors.HexColor('#555555')
COR_BORDA = colors.HexColor('#999999')
COR_BORDA_ESCURA = colors.HexColor('#333333')


def get_styles():
    """Estilos Paragraph padronizados da DANFSe."""
    styles = getSampleStyleSheet()
    s = {
        'faixa': ParagraphStyle(
            'faixa', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=8,
            textColor=colors.black, alignment=TA_LEFT,
            leading=10,
        ),
        'label': ParagraphStyle(
            'label', parent=styles['Normal'],
            fontName='Helvetica', fontSize=6.5,
            textColor=COR_LABEL, alignment=TA_LEFT,
            leading=8,
        ),
        'valor': ParagraphStyle(
            'valor', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=7.5,
            textColor=colors.black, alignment=TA_LEFT,
            leading=9,
        ),
        'valor_normal': ParagraphStyle(
            'valor_normal', parent=styles['Normal'],
            fontName='Helvetica', fontSize=7.5,
            textColor=colors.black, alignment=TA_LEFT,
            leading=9,
        ),
        'valor_right': ParagraphStyle(
            'valor_right', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=7.5,
            textColor=colors.black, alignment=TA_RIGHT,
            leading=9,
        ),
        # Estilo destacado (vermelho + negrito) usado APENAS quando há
        # efetivamente uma retenção tributária a ser exibida (ISSQN, IRRF,
        # INSS/CP, CSLL, PIS/COFINS retidos, total das retenções federais).
        'valor_retencao': ParagraphStyle(
            'valor_retencao', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=7.5,
            textColor=colors.red, alignment=TA_LEFT,
            leading=9,
        ),
        'titulo_center': ParagraphStyle(
            'titulo_center', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=10,
            textColor=colors.black, alignment=TA_CENTER,
            leading=12,
        ),
        'titulo_danfse': ParagraphStyle(
            'titulo_danfse', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=14,
            textColor=colors.black, alignment=TA_LEFT,
            leading=16,
        ),
        'pequeno': ParagraphStyle(
            'pequeno', parent=styles['Normal'],
            fontName='Helvetica', fontSize=6,
            textColor=colors.black, alignment=TA_LEFT,
            leading=7.5,
        ),
        'pequeno_center': ParagraphStyle(
            'pequeno_center', parent=styles['Normal'],
            fontName='Helvetica', fontSize=6,
            textColor=colors.black, alignment=TA_CENTER,
            leading=7.5,
        ),
        'pequeno_bold': ParagraphStyle(
            'pequeno_bold', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=6.5,
            textColor=colors.black, alignment=TA_LEFT,
            leading=8,
        ),
        'descr_servico': ParagraphStyle(
            'descr_servico', parent=styles['Normal'],
            fontName='Helvetica', fontSize=7.5,
            textColor=colors.black, alignment=TA_LEFT,
            leading=9,
        ),
        'chave': ParagraphStyle(
            'chave', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=8.5,
            textColor=colors.black, alignment=TA_CENTER,
            leading=10,
        ),
        'info_topo': ParagraphStyle(
            'info_topo', parent=styles['Normal'],
            fontName='Helvetica', fontSize=7,
            textColor=colors.black, alignment=TA_LEFT,
            leading=8.5,
        ),
    }
    return s


def campo(label, valor, style_label, style_valor):
    """Retorna lista [Paragraph(label), Paragraph(valor)] para compor célula."""
    if valor in (None, ''):
        valor = '-'
    return [Paragraph(label, style_label), Paragraph(str(valor), style_valor)]


def secao_faixa(texto, largura, style):
    """Tabela de 1 linha representando a faixa cinza de seção."""
    t = Table([[Paragraph(texto, style)]], colWidths=[largura])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_TITULO_FAIXA),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def montar_cabecalho(data, styles, largura_util):
    """Monta o bloco superior com DANFSe + chave + QR + números."""
    chave = data['chave_acesso']
    # Formata chave em grupos de 4
    chave_fmt = ' '.join([chave[i:i+4] for i in range(0, len(chave), 4)]) if chave else ''

    # QR Code
    try:
        qr_buf = gerar_qrcode(chave)
        qr_img = RLImage(qr_buf, width=26*mm, height=26*mm)
    except Exception:
        qr_img = Paragraph("QR", styles['pequeno_center'])

    # --- Linha topo: DANFSe | "Documento Auxiliar da NFS-e" | Município emissor
    municipio_emissor = data.get('xLocEmi', '-') or '-'

    topo_esq = [
        Paragraph("DANFSe v1.0", styles['titulo_danfse']),
        Paragraph("Documento Auxiliar da NFS-e", styles['pequeno']),
    ]
    topo_centro = [
        Paragraph(f"<b>Prefeitura Municipal de {municipio_emissor}</b>", styles['titulo_center']),
        Paragraph("Secretaria de Finanças - Departamento Técnico de Fiscalização Tributária",
                  styles['pequeno_center']),
    ]
    topo_dir = [
        Paragraph("<b>Chave de Acesso da NFS-e</b>", styles['pequeno_bold']),
        Paragraph(chave_fmt if chave_fmt else '-', styles['chave']),
        Paragraph("A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR "
                  "ou pela consulta da chave de acesso no portal nacional da NFS-e",
                  styles['pequeno']),
    ]

    # Coluna direita: texto à esquerda + QR à direita (lado a lado)
    texto_chave_col = [
        Paragraph("<b>Chave de Acesso da NFS-e</b>", styles['pequeno_bold']),
        Paragraph(chave_fmt if chave_fmt else '-', styles['chave']),
        Spacer(1, 2),
        Paragraph("A autenticidade desta NFS-e pode ser verificada pela leitura "
                  "deste código QR ou pela consulta da chave de acesso no portal "
                  "nacional da NFS-e", styles['pequeno']),
    ]
    sub_tab_dir = Table(
        [[texto_chave_col, qr_img]],
        colWidths=[largura_util*0.40*0.70, largura_util*0.40*0.30]
    )
    sub_tab_dir.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    t_topo = Table(
        [[topo_esq, topo_centro, sub_tab_dir]],
        colWidths=[largura_util*0.22, largura_util*0.38, largura_util*0.40]
    )
    t_topo.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    # --- Linha 2: números da NFS-e (Número, Competência, Data/Hora emissão, nº DPS, Série, Data DPS)
    numero_nfse = data.get('nNFSe', '-')
    competencia = fmt_data(data['dps'].get('dCompet', ''))
    dh_emi_nfse = fmt_datahora(data.get('dhProc', ''))
    numero_dps = data['dps'].get('nDPS', '-')
    serie_dps = data['dps'].get('serie', '-')
    dh_emi_dps = fmt_datahora(data['dps'].get('dhEmi', ''))

    row = [
        campo("Número da NFS-e", numero_nfse, styles['label'], styles['valor']),
        campo("Competência da NFS-e", competencia, styles['label'], styles['valor']),
        campo("Data e Hora da emissão da NFS-e", dh_emi_nfse, styles['label'], styles['valor']),
        campo("Número da DPS", numero_dps, styles['label'], styles['valor']),
        campo("Série da DPS", serie_dps, styles['label'], styles['valor']),
        campo("Data e Hora da emissão da DPS", dh_emi_dps, styles['label'], styles['valor']),
    ]
    t_nums = Table([row], colWidths=[largura_util/6]*6)
    t_nums.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    return [t_topo, Spacer(1, 2), t_nums]


def montar_bloco_participante(tipo, part, styles, largura_util, identificado_flag=True,
                              mostrar_simples=False):
    """
    Monta o bloco do participante (emitente, tomador ou intermediário).
    tipo: 'emitente' | 'tomador' | 'intermediario'
    """
    if tipo == 'emitente':
        titulo_faixa = "EMITENTE DA NFS-e"
        subtitulo = "Prestador do Serviço"
    elif tipo == 'tomador':
        titulo_faixa = "TOMADOR DO SERVIÇO"
        subtitulo = None
    else:
        titulo_faixa = "INTERMEDIÁRIO DO SERVIÇO"
        subtitulo = None

    if not identificado_flag:
        faixa = Table(
            [[Paragraph(f"{titulo_faixa} NÃO IDENTIFICADO NA NFS-e", styles['faixa'])]],
            colWidths=[largura_util]
        )
        faixa.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COR_TITULO_FAIXA),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return [faixa]

    # --- Faixa de título ---
    faixa = secao_faixa(titulo_faixa, largura_util, styles['faixa'])

    # --- Dados básicos ---
    # Documento: CNPJ > CPF > NIF
    doc_raw = part.get('CNPJ') or part.get('CPF') or part.get('NIF') or ''
    doc_fmt = fmt_cnpj_cpf(doc_raw) if doc_raw else '-'
    im = part.get('IM', '') or '-'
    fone = fmt_fone(part.get('fone', ''))
    nome = part.get('xNome', '') or '-'
    email = part.get('email', '') or '-'

    # Endereço
    xLgr = part.get('xLgr', '')
    nro = part.get('nro', '')
    xCpl = part.get('xCpl', '')
    xBairro = part.get('xBairro', '')
    end_partes = []
    if xLgr:
        end_partes.append(xLgr)
    if nro:
        end_partes.append(nro)
    if xCpl:
        end_partes.append(xCpl)
    if xBairro:
        end_partes.append(xBairro)
    endereco = ', '.join(end_partes) if end_partes else '-'

    # Município
    cmun = part.get('cMun', '')
    uf = part.get('UF', '')
    nome_mun, uf_map = municipio_por_ibge(cmun)
    if uf and uf != '':
        mun_str = f"{nome_mun} - {uf}" if nome_mun != '-' else '-'
    elif uf_map:
        mun_str = f"{nome_mun} - {uf_map}"
    else:
        mun_str = nome_mun if nome_mun != '-' else '-'

    cep = fmt_cep(part.get('CEP', ''))

    # Subtítulo (só emitente)
    rows = []
    if subtitulo:
        rows.append([Paragraph(subtitulo, styles['pequeno_bold']), '', '', ''])

    # Linha 1: CNPJ | IM | Telefone
    rows.append([
        campo("CNPJ / CPF / NIF", doc_fmt, styles['label'], styles['valor']),
        campo("Inscrição Municipal", im, styles['label'], styles['valor']),
        campo("Telefone", fone, styles['label'], styles['valor']),
        '',
    ])

    # Linha 2: Nome (ocupa duas colunas) | E-mail
    rows.append([
        campo("Nome / Nome Empresarial", nome, styles['label'], styles['valor']),
        '',
        campo("E-mail", email, styles['label'], styles['valor']),
        '',
    ])

    # Linha 3: Endereço | Município | CEP
    rows.append([
        campo("Endereço", endereco, styles['label'], styles['valor']),
        '',
        campo("Município", mun_str, styles['label'], styles['valor']),
        campo("CEP", cep, styles['label'], styles['valor']),
    ])

    # Linha 4 (só emitente): Simples Nacional + Regime SN
    if mostrar_simples and tipo == 'emitente':
        sn_desc = OPSIMPNAC_DESC.get(part.get('opSimpNac', ''), '-')
        reg_sn_desc = REGAPTRIBSN_DESC.get(part.get('regApTribSN', ''), '-')
        rows.append([
            campo("Simples Nacional na Data de Competência", sn_desc,
                  styles['label'], styles['valor']),
            '',
            campo("Regime de Apuração Tributária pelo SN", reg_sn_desc,
                  styles['label'], styles['valor']),
            '',
        ])

    # Define colWidths baseado em 4 colunas
    cols = [largura_util*0.28, largura_util*0.22, largura_util*0.30, largura_util*0.20]
    # Ajustes de span
    style_cmds = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]

    # Para emitente:
    offset = 0
    if subtitulo:
        # Primeira linha span em 4 colunas
        style_cmds.append(('SPAN', (0, 0), (-1, 0)))
        style_cmds.append(('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f7f7f7')))
        offset = 1

    # Linha 2 (linha de nome): nome span em 2 colunas, email span em 2 colunas
    style_cmds.append(('SPAN', (0, offset+1), (1, offset+1)))
    style_cmds.append(('SPAN', (2, offset+1), (3, offset+1)))

    # Linha 3 (linha endereço): endereço span em 2 colunas
    style_cmds.append(('SPAN', (0, offset+2), (1, offset+2)))

    # Linha 4 (Simples Nacional): cada campo span em 2 colunas
    if mostrar_simples and tipo == 'emitente':
        style_cmds.append(('SPAN', (0, offset+3), (1, offset+3)))
        style_cmds.append(('SPAN', (2, offset+3), (3, offset+3)))

    bloco = Table(rows, colWidths=cols)
    bloco.setStyle(TableStyle(style_cmds))

    return [faixa, bloco]


def montar_bloco_servico(data, styles, largura_util):
    """Seção SERVIÇO PRESTADO."""
    faixa = secao_faixa("SERVIÇO PRESTADO", largura_util, styles['faixa'])

    serv = data['serv']
    dps = data['dps']

    # Código Tributação Nacional (formatado XX.XX.XX)
    ctrib_nac_cod = fmt_codtrib(serv.get('cTribNac', ''))
    ctrib_nac_desc = data.get('xTribNac', '') or ''
    ctrib_nac_full = f"{ctrib_nac_cod} - {ctrib_nac_desc[:60]}" if ctrib_nac_desc else ctrib_nac_cod

    ctrib_mun_cod = serv.get('cTribMun', '')
    ctrib_mun_desc = data.get('xTribMun', '') or ''
    ctrib_mun_full = (f"{ctrib_mun_cod} - {ctrib_mun_desc[:60]}"
                      if ctrib_mun_cod and ctrib_mun_desc
                      else (ctrib_mun_cod or '-'))

    # Local da prestação
    cLocPrest = serv.get('cLocPrestacao', '')
    mun_prest, uf_prest = municipio_por_ibge(cLocPrest)
    if uf_prest:
        local_prest = f"{mun_prest} - {uf_prest}"
    else:
        local_prest = data.get('xLocPrestacao', mun_prest)
    pais_prest = serv.get('cPaisPrestacao', '') or '-'

    # Linha 1: Código Tributação Nacional | Código Tributação Municipal
    row1 = Table(
        [[
            campo("Código de Tributação Nacional", ctrib_nac_full,
                  styles['label'], styles['valor']),
            campo("Código de Tributação Municipal", ctrib_mun_full,
                  styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util*0.50, largura_util*0.50]
    )
    row1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    # Linha 2: Local da Prestação | País da Prestação | Código NBS
    nbs = serv.get('cNBS', '') or '-'
    row2 = Table(
        [[
            campo("Local da Prestação", local_prest, styles['label'], styles['valor']),
            campo("País da Prestação", pais_prest, styles['label'], styles['valor']),
            campo("Código NBS", nbs, styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util*0.50, largura_util*0.25, largura_util*0.25]
    )
    row2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    # Linha 3: Descrição do Serviço
    xDescServ = serv.get('xDescServ', '') or '-'
    # Preserva quebras de linha do XML
    xDescServ_html = xDescServ.replace('\n', '<br/>').replace('\r', '')
    descricao_block = [
        Paragraph("Descrição do Serviço", styles['label']),
        Paragraph(xDescServ_html, styles['descr_servico']),
    ]

    row3 = Table([[descricao_block]], colWidths=[largura_util])
    row3.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    return [faixa, row1, row2, row3]


def montar_bloco_tributacao_municipal(data, styles, largura_util):
    """Seção TRIBUTAÇÃO MUNICIPAL (ISSQN)."""
    faixa = secao_faixa("TRIBUTAÇÃO MUNICIPAL", largura_util, styles['faixa'])

    vals = data['valores_dps']
    vals_nfse = data['valores_nfse']

    # Tributação do ISSQN
    tribissqn = TRIBISSQN_DESC.get(vals.get('tribISSQN', ''), '-')
    # País resultado da prestação (só preenchido em caso de exportação - tribISSQN=3)
    cPaisResult = vals.get('cPaisResult', '')
    pais_result = cPaisResult if cPaisResult else '-'
    # Município de incidência
    mun_incid = data.get('xLocIncid', '') or '-'
    cmun_incid = data.get('cLocIncid', '')
    if cmun_incid:
        nm, uf = municipio_por_ibge(cmun_incid)
        if uf:
            mun_incid = f"{nm} - {uf}"
    # Regime Especial
    reg_esp = REGESP_DESC.get(data['prest'].get('regEspTrib', ''), '-')
    tp_imune = vals.get('tpImunidade', '') or '-'

    # Suspensão da exigibilidade (estrutura oficial exigSusp com tpSusp/nProcesso)
    # Fallback para os campos antigos (exigISSQN/nProcSusp) quando presentes
    tpSusp = vals.get('tpSusp', '')
    exigissqn_old = vals.get('exigISSQN', '')
    if tpSusp:
        if tpSusp == '1':
            suspensao = 'Sim (Decisão Judicial)'
        elif tpSusp == '2':
            suspensao = 'Sim (Processo Administrativo)'
        else:
            suspensao = 'Sim'
    else:
        # compat: campo antigo exigISSQN (1=normal, outros = suspenso)
        suspensao = 'Não' if exigissqn_old in ('', '1') else 'Sim'
    n_proc_susp = vals.get('nProcesso', '') or vals.get('nProcSusp', '') or '-'

    # Benefício municipal
    tp_benef = vals.get('tpBenef', '') or vals.get('nBM', '') or '-'

    # Valores
    vServ = vals.get('vServ', '0.00') or '0.00'
    vDescIncond = vals.get('vDescIncond', '') or '-'
    vDR = vals.get('vDR', '') or '-'
    vBC = vals_nfse.get('vBC', '') or '-'
    pAliq = vals_nfse.get('pAliqAplic', '') or vals.get('pAliq', '')
    pAliq_fmt = fmt_perc(pAliq) if pAliq else '-'
    tpRet = TPRETISSQN_DESC.get(vals.get('tpRetISSQN', ''), '-')
    vISSQN = vals_nfse.get('vISSQN', '') or '-'

    # ---- Linha 1
    row1 = Table(
        [[
            campo("Tributação do ISSQN", tribissqn, styles['label'], styles['valor']),
            campo("País Resultado da Prestação do Serviço", pais_result,
                  styles['label'], styles['valor']),
            campo("Município de Incidência do ISSQN", mun_incid,
                  styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util*0.33, largura_util*0.33, largura_util*0.34]
    )
    # ---- Linha 2
    row2 = Table(
        [[
            campo("Regime Especial de Tributação", reg_esp, styles['label'], styles['valor']),
            campo("Tipo de Imunidade", tp_imune, styles['label'], styles['valor']),
            campo("Suspensão da Exigibilidade do ISSQN", suspensao,
                  styles['label'], styles['valor']),
            campo("Número Processo Suspensão", n_proc_susp,
                  styles['label'], styles['valor']),
            campo("Benefício Municipal", tp_benef, styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util*0.22, largura_util*0.16, largura_util*0.24,
                   largura_util*0.22, largura_util*0.16]
    )
    # ---- Linha 3
    row3 = Table(
        [[
            campo("Valor do Serviço",
                  fmt_moeda(vServ) if vServ not in ('', '-') else '-',
                  styles['label'], styles['valor']),
            campo("Desconto Incondicionado",
                  fmt_moeda(vDescIncond) if vDescIncond not in ('', '-', '0.00') else '-',
                  styles['label'], styles['valor']),
            campo("Total Deduções/Reduções",
                  fmt_moeda(vDR) if vDR not in ('', '-', '0.00') else '-',
                  styles['label'], styles['valor']),
            campo("Cálculo do BM", '-', styles['label'], styles['valor']),
            campo("BC ISSQN",
                  fmt_moeda(vBC) if vBC not in ('', '-') else '-',
                  styles['label'], styles['valor']),
            campo("Alíquota Aplicada", pAliq_fmt, styles['label'], styles['valor']),
            campo("Retenção do ISSQN", tpRet, styles['label'], styles['valor']),
            campo("ISSQN Apurado",
                  fmt_moeda(vISSQN) if vISSQN not in ('', '-') else '-',
                  styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util/8]*8
    )
    for t in [row1, row2, row3]:
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

    return [faixa, row1, row2, row3]


def montar_bloco_tributacao_federal(data, styles, largura_util):
    """Seção TRIBUTAÇÃO FEDERAL."""
    faixa = secao_faixa("TRIBUTAÇÃO FEDERAL", largura_util, styles['faixa'])

    vals = data['valores_dps']

    irrf = vals.get('vRetIRRF', '')
    cp = vals.get('vRetCP', '')
    csll = vals.get('vRetCSLL', '')
    tp_ret_pc = vals.get('tpRetPisCofins', '')
    # Exibe código + texto (ex.: "1 - Retido") como no DANFSe oficial
    if tp_ret_pc:
        base_desc = TPRETPISCOFINS_DESC.get(tp_ret_pc, 'Não especificado')
        desc_contrib_soc = f"{tp_ret_pc} - {base_desc}"
    else:
        desc_contrib_soc = '-'
    vPis = vals.get('vPis', '')
    vCofins = vals.get('vCofins', '')

    # Determina, para cada campo, se há efetivamente uma retenção tributária
    # (valor > 0). Em caso positivo, o valor é exibido em vermelho e negrito.
    pis_cofins_retidos = tp_ret_pc in ('1', '3', '4')
    style_irrf = styles['valor_retencao'] if _eh_retencao(irrf) else styles['valor']
    style_cp = styles['valor_retencao'] if _eh_retencao(cp) else styles['valor']
    style_csll = styles['valor_retencao'] if _eh_retencao(csll) else styles['valor']
    style_pis = (styles['valor_retencao']
                 if pis_cofins_retidos and _eh_retencao(vPis)
                 else styles['valor'])
    style_cofins = (styles['valor_retencao']
                    if pis_cofins_retidos and _eh_retencao(vCofins)
                    else styles['valor'])

    # Para o DANFSe do exemplo: CSLL é "Contribuições Sociais - Retidas"
    # Contrib Previdenciária = vRetCP
    row1 = Table(
        [[
            campo("IRRF",
                  fmt_moeda(irrf) if irrf not in ('', '-', '0.00') else '-',
                  styles['label'], style_irrf),
            campo("Contribuição Previdenciária - Retida",
                  fmt_moeda(cp) if cp not in ('', '-', '0.00') else '-',
                  styles['label'], style_cp),
            campo("Contribuições Sociais - Retidas",
                  fmt_moeda(csll) if csll not in ('', '-', '0.00') else '-',
                  styles['label'], style_csll),
            campo("Descrição Contrib. Sociais - Retidas",
                  desc_contrib_soc, styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util*0.17, largura_util*0.28, largura_util*0.25, largura_util*0.30]
    )
    row2 = Table(
        [[
            campo("PIS - Débito Apuração Própria",
                  fmt_moeda(vPis) if vPis not in ('', '-', '0.00') else '-',
                  styles['label'], style_pis),
            campo("COFINS - Débito Apuração Própria",
                  fmt_moeda(vCofins) if vCofins not in ('', '-', '0.00') else '-',
                  styles['label'], style_cofins),
        ]],
        colWidths=[largura_util*0.50, largura_util*0.50]
    )
    for t in [row1, row2]:
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

    return [faixa, row1, row2]


def montar_bloco_valor_total(data, styles, largura_util):
    """Seção VALOR TOTAL DA NFS-e."""
    faixa = secao_faixa("VALOR TOTAL DA NFS-E", largura_util, styles['faixa'])

    vals = data['valores_dps']
    vals_nfse = data['valores_nfse']

    vServ = vals.get('vServ', '')
    vDescCond = vals.get('vDescCond', '')
    vDescIncond = vals.get('vDescIncond', '')

    # Verifica se ISSQN foi retido
    tpRet_val = vals.get('tpRetISSQN', '')
    vISSQN_total = vals_nfse.get('vISSQN', '')
    issqn_retido = (fmt_moeda(vISSQN_total)
                    if tpRet_val in ('2', '3') and vISSQN_total
                    else '-')

    # Total retenções federais (IRRF + CP + CSLL + PIS + COFINS se retidos).
    # IMPORTANTE: este campo deve conter SOMENTE retenções federais. NÃO usar
    # `vTotalRet` do XML como fallback, pois ele representa o total de TODAS
    # as retenções, incluindo o ISSQN (municipal) — o que faria o valor do
    # ISS aparecer indevidamente no campo "Total das Retenções Federais".
    # Leiaute oficial: tpRetPisCofins 1=Retido, 2=Não Retido.
    # Compat: mantemos também códigos antigos (3 e 4) usados em XMLs pré-NT007.
    try:
        total_ret_fed = 0.0
        for k in ['vRetIRRF', 'vRetCP', 'vRetCSLL']:
            v = vals.get(k, '')
            if v and v not in ('-',):
                try:
                    total_ret_fed += float(v)
                except (ValueError, TypeError):
                    pass
        # Se PIS/COFINS retidos (1=oficial, 3/4=compat)
        if vals.get('tpRetPisCofins', '') in ('1', '3', '4'):
            if vals.get('vPis', ''):
                try:
                    total_ret_fed += float(vals['vPis'])
                except (ValueError, TypeError):
                    pass
            if vals.get('vCofins', ''):
                try:
                    total_ret_fed += float(vals['vCofins'])
                except (ValueError, TypeError):
                    pass
        if total_ret_fed > 0:
            total_ret_fed_str = fmt_moeda(total_ret_fed)
        else:
            # Sem retenções federais → exibe '-'.
            # NÃO usar vTotalRet (inclui ISSQN municipal).
            total_ret_fed_str = '-'
    except Exception:
        total_ret_fed_str = '-'

    # PIS/COFINS Débito Apur. Própria (quando não retidos)
    # Leiaute oficial: tpRetPisCofins=2 significa "Não Retido" => débito próprio
    # Compat: códigos 0 (aparece em XMLs reais) tratado igualmente como não retido
    pis_cofins_debito = '-'
    if vals.get('tpRetPisCofins', '') in ('0', '2'):
        try:
            soma = 0.0
            if vals.get('vPis', ''):
                soma += float(vals['vPis'])
            if vals.get('vCofins', ''):
                soma += float(vals['vCofins'])
            if soma > 0:
                pis_cofins_debito = fmt_moeda(soma)
        except Exception:
            pass

    vLiq = vals_nfse.get('vLiq', '') or vServ

    # Destaque visual (vermelho + negrito) quando há retenção
    style_issqn_ret = (styles['valor_retencao']
                       if _eh_retencao(vISSQN_total) and tpRet_val in ('2', '3')
                       else styles['valor'])
    style_total_ret_fed = (styles['valor_retencao']
                           if total_ret_fed > 0
                           else styles['valor'])

    row1 = Table(
        [[
            campo("Valor do Serviço",
                  fmt_moeda(vServ) if vServ else '-',
                  styles['label'], styles['valor']),
            campo("Desconto Condicionado",
                  fmt_moeda(vDescCond) if vDescCond not in ('', '-', '0.00') else '-',
                  styles['label'], styles['valor']),
            campo("Desconto Incondicionado",
                  fmt_moeda(vDescIncond) if vDescIncond not in ('', '-', '0.00') else '-',
                  styles['label'], styles['valor']),
            campo("ISSQN Retido", issqn_retido, styles['label'], style_issqn_ret),
        ]],
        colWidths=[largura_util*0.25]*4
    )
    row2 = Table(
        [[
            campo("Total das Retenções Federais", total_ret_fed_str,
                  styles['label'], style_total_ret_fed),
            campo("PIS/COFINS - Débito Apur. Própria", pis_cofins_debito,
                  styles['label'], styles['valor']),
            campo("Valor Líquido da NFS-e",
                  fmt_moeda(vLiq) if vLiq else '-',
                  styles['label'], styles['valor_right']),
        ]],
        colWidths=[largura_util*0.34, largura_util*0.33, largura_util*0.33]
    )
    for t in [row1, row2]:
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

    return [faixa, row1, row2]


def montar_bloco_totais_aproximados(data, styles, largura_util):
    """
    Seção TOTAIS APROXIMADOS DOS TRIBUTOS (Fonte: IBPT).
    Suporta três formatos do leiaute nacional:
      - grupo `vTotTrib`  → valores em R$ (vTotTribFed, vTotTribEst, vTotTribMun)
      - grupo `pTotTrib`  → percentuais (pTotTribFed, pTotTribEst, pTotTribMun)
                            → usado tipicamente no Lucro Presumido/Real
      - campo `pTotTribSN` → percentual único (Simples Nacional)
    Quando há apenas percentual, calcula o valor aplicando sobre vServ.
    """
    faixa = secao_faixa("TOTAIS APROXIMADOS DOS TRIBUTOS", largura_util, styles['faixa'])

    vals = data['valores_dps']
    # Valores absolutos (R$)
    vFed = vals.get('vTotTribFed', '') or ''
    vEst = vals.get('vTotTribEst', '') or ''
    vMun = vals.get('vTotTribMun', '') or ''
    # Percentuais (%) - NT 004/007
    pFed = vals.get('pTotTribFed', '') or ''
    pEst = vals.get('pTotTribEst', '') or ''
    pMun = vals.get('pTotTribMun', '') or ''
    # Percentual único do Simples Nacional
    pSN = vals.get('pTotTribSN', '') or ''
    # Valor do serviço (base para calcular valor aproximado a partir do percentual)
    vServ = vals.get('vServ', '') or ''

    def _to_float(v):
        try:
            return float(v) if v not in ('', None, '-') else 0.0
        except Exception:
            return 0.0

    vServ_f = _to_float(vServ)

    def calcula_apresentacao(v_abs, p_perc):
        """
        Retorna string "R$ X.XXX,XX (Y,YY%)" combinando valor e percentual.
        Se só houver percentual, calcula valor aplicando sobre vServ.
        Se só houver valor, calcula percentual inverso.
        """
        v_abs_f = _to_float(v_abs)
        p_perc_f = _to_float(p_perc)

        tem_valor = v_abs_f > 0
        tem_perc = p_perc_f > 0

        # Se tem só percentual, calcula valor a partir de vServ
        if tem_perc and not tem_valor and vServ_f > 0:
            v_abs_f = vServ_f * p_perc_f / 100.0
            tem_valor = True
        # Se tem só valor, calcula percentual inverso
        elif tem_valor and not tem_perc and vServ_f > 0:
            p_perc_f = (v_abs_f / vServ_f) * 100.0
            tem_perc = True

        if not tem_valor and not tem_perc:
            return '-'

        partes = []
        if tem_valor:
            partes.append(fmt_moeda(v_abs_f))
        if tem_perc:
            partes.append(f"({fmt_num(p_perc_f, 2)}%)")
        return ' '.join(partes)

    fed_txt = calcula_apresentacao(vFed, pFed)
    est_txt = calcula_apresentacao(vEst, pEst)
    mun_txt = calcula_apresentacao(vMun, pMun)

    row = Table(
        [[
            campo("Federais", fed_txt, styles['label'], styles['valor']),
            campo("Estaduais", est_txt, styles['label'], styles['valor']),
            campo("Municipais", mun_txt, styles['label'], styles['valor']),
        ]],
        colWidths=[largura_util/3]*3
    )
    row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    partes = [faixa, row]

    # Linha auxiliar com fonte / carga consolidada
    textos_rodape = []
    if pSN:
        valor_sn = vServ_f * _to_float(pSN) / 100.0
        textos_rodape.append(
            f"<b>Carga Tributária Aproximada (Simples Nacional):</b> "
            f"{fmt_perc(pSN)} do valor do serviço "
            f"({fmt_moeda(valor_sn) if valor_sn > 0 else '-'}) — Fonte: IBPT"
        )

    # Fonte IBPT também para Lucro Real/Presumido quando há percentuais
    if (pFed or pEst or pMun) and not pSN:
        # Calcula total consolidado
        total_perc = _to_float(pFed) + _to_float(pEst) + _to_float(pMun)
        if total_perc > 0 and vServ_f > 0:
            valor_total = vServ_f * total_perc / 100.0
            textos_rodape.append(
                f"<b>Carga Tributária Aproximada Total:</b> "
                f"{fmt_num(total_perc, 2)}% do valor do serviço "
                f"({fmt_moeda(valor_total)}) — Fonte: IBPT "
                f"(Lei 12.741/2012)"
            )

    if textos_rodape:
        linha_rodape = Table(
            [[Paragraph("<br/>".join(textos_rodape), styles['pequeno'])]],
            colWidths=[largura_util]
        )
        linha_rodape.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        partes.append(linha_rodape)

    return partes


def montar_bloco_informacoes_complementares(data, styles, largura_util):
    """Seção INFORMAÇÕES COMPLEMENTARES."""
    faixa = secao_faixa("INFORMAÇÕES COMPLEMENTARES", largura_util, styles['faixa'])

    xInfComp = data['serv'].get('xInfComp', '') or ''
    ibscbs = data.get('ibscbs_nfse')

    partes_texto = []
    if xInfComp:
        partes_texto.append(f"<b>Inf. Complementares:</b> {xInfComp}")

    if ibscbs:
        vBC = ibscbs.get('vBC', '')
        pIBSUF = ibscbs.get('pIBSUF', '')
        pIBSMun = ibscbs.get('pIBSMun', '')
        pCBS = ibscbs.get('pCBS', '')
        vIBSUF = ibscbs.get('vIBSUF', '')
        vIBSMun = ibscbs.get('vIBSMun', '')
        vCBS = ibscbs.get('vCBS', '')

        # Só monta bloco IBS/CBS se tiver dados
        if any([vBC, pIBSUF, pCBS, vCBS]):
            ibs_txt = (
                f"<b>Cálculo IBS/CBS:</b> "
                f"Base Cálc.: {fmt_moeda(vBC) if vBC else '-'} | "
                f"IBS UF: {fmt_perc(pIBSUF)} ({fmt_moeda(vIBSUF) if vIBSUF else 'R$ 0,00'}) | "
                f"IBS Mun: {fmt_perc(pIBSMun)} ({fmt_moeda(vIBSMun) if vIBSMun else 'R$ 0,00'}) | "
                f"CBS: {fmt_perc(pCBS)} ({fmt_moeda(vCBS) if vCBS else 'R$ 0,00'})"
            )
            partes_texto.append(ibs_txt)

    nbs = data['serv'].get('cNBS', '')
    if nbs:
        partes_texto.append(f"<b>NBS:</b> {nbs}")

    if not partes_texto:
        partes_texto.append("-")

    texto_final = "<br/><br/>".join(partes_texto)

    bloco = Table(
        [[Paragraph(texto_final, styles['pequeno'])]],
        colWidths=[largura_util]
    )
    bloco.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    return [faixa, bloco]


# =============================================================================
# FUNÇÃO PRINCIPAL DE GERAÇÃO DO PDF
# =============================================================================
def gerar_pdf_danfse(data, pdf_path):
    """Gera o PDF da DANFSe a partir do dicionário extraído do XML."""

    # Merge das infos de regime tributário do prestador para o emitente.
    # Isso garante que campos como Simples Nacional (MEI, ME/EPP) apareçam
    # corretamente no bloco do emitente do PDF, independentemente de quem
    # chama esta função (interface desktop, site via Pyodide, etc.).
    # Antes esse merge ficava só na função wrapper do desktop; o site
    # chamava `gerar_pdf_danfse` diretamente e o campo ficava vazio.
    if 'emit' in data and 'prest' in data:
        data['emit']['opSimpNac'] = data['prest'].get('opSimpNac', '')
        data['emit']['regApTribSN'] = data['prest'].get('regApTribSN', '')
        data['emit']['regEspTrib'] = data['prest'].get('regEspTrib', '')

    margem = 8 * mm
    largura_pagina, altura_pagina = A4
    largura_util = largura_pagina - 2 * margem

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=margem, rightMargin=margem,
        topMargin=margem, bottomMargin=margem,
        title=f"DANFSe - NFS-e {data.get('nNFSe', '')}",
        author="DANFSe Generator",
    )

    styles = get_styles()
    story = []

    # --- Cabeçalho (topo + numeração) ---
    story.extend(montar_cabecalho(data, styles, largura_util))
    story.append(Spacer(1, 3))

    # --- Emitente ---
    story.extend(
        montar_bloco_participante('emitente', data['emit'], styles, largura_util,
                                  identificado_flag=True, mostrar_simples=True)
    )
    # Adiciona os dados do Simples Nacional que vêm do prest
    # (já feito via mostrar_simples, mas precisa passar os dados do regime)
    # Atualização: mesclar dados de emit + prest para mostrar_simples
    story.append(Spacer(1, 2))

    # --- Tomador ---
    if data['toma'].get('identificado'):
        story.extend(
            montar_bloco_participante('tomador', data['toma'], styles, largura_util,
                                      identificado_flag=True)
        )
    else:
        story.extend(
            montar_bloco_participante('tomador', {}, styles, largura_util,
                                      identificado_flag=False)
        )
    story.append(Spacer(1, 2))

    # --- Intermediário ---
    if data['interm'].get('identificado'):
        story.extend(
            montar_bloco_participante('intermediario', data['interm'], styles, largura_util,
                                      identificado_flag=True)
        )
    else:
        story.extend(
            montar_bloco_participante('intermediario', {}, styles, largura_util,
                                      identificado_flag=False)
        )
    story.append(Spacer(1, 2))

    # --- Serviço Prestado ---
    story.extend(montar_bloco_servico(data, styles, largura_util))
    story.append(Spacer(1, 2))

    # --- Tributação Municipal ---
    story.extend(montar_bloco_tributacao_municipal(data, styles, largura_util))
    story.append(Spacer(1, 2))

    # --- Tributação Federal ---
    story.extend(montar_bloco_tributacao_federal(data, styles, largura_util))
    story.append(Spacer(1, 2))

    # --- Valor Total da NFS-e ---
    story.extend(montar_bloco_valor_total(data, styles, largura_util))
    story.append(Spacer(1, 2))

    # --- Totais Aproximados dos Tributos ---
    story.extend(montar_bloco_totais_aproximados(data, styles, largura_util))
    story.append(Spacer(1, 2))

    # --- Informações Complementares ---
    story.extend(montar_bloco_informacoes_complementares(data, styles, largura_util))

    # Rodapé em todas as páginas
    def _rodape(cnv, doc_):
        cnv.saveState()
        cnv.setFont('Helvetica', 6)
        cnv.setFillColor(colors.grey)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        rodape_txt = (f"Documento Auxiliar da Nota Fiscal de Serviços Eletrônica "
                      f"(DANFSe) - Padrão Nacional  |  "
                      f"Gerado em {agora}  |  "
                      f"Página {cnv.getPageNumber()}")
        cnv.drawCentredString(largura_pagina/2, 5*mm, rodape_txt)
        cnv.restoreState()

    # Para mesclar prest (Simples Nacional) com emitente
    # aproveitamos o bloco emitente para ler data['prest']
    # Ajuste: em vez de adicionar no bloco_participante, fazemos merge aqui
    # (nao necessário se fizemos via mostrar_simples e merge manual)
    # Vamos ajustar: mesclar prest em emit
    pass

    doc.build(story, onFirstPage=_rodape, onLaterPages=_rodape)


# =============================================================================
# INTERFACE GRÁFICA (TKINTER)
# =============================================================================
def _processar_xml_individual(xml_path, pasta_destino):
    """
    Processa um único XML e gera o PDF correspondente.
    Retorna (sucesso: bool, mensagem: str, pdf_path: str|None).
    """
    try:
        data = parse_nfse(xml_path)

        # Merge prest em emit para exibir Simples Nacional no bloco do emitente
        data['emit']['opSimpNac'] = data['prest'].get('opSimpNac', '')
        data['emit']['regApTribSN'] = data['prest'].get('regApTribSN', '')

        # Nome base do PDF: DANFSe_<chave>.pdf (ou fallback)
        chave = data.get('chave_acesso', '')
        if chave:
            nome_base = f"DANFSe_{chave}"
        else:
            nNFSe = data.get('nNFSe', '') or 'sem_numero'
            # Evita conflito entre notas sem chave usando também nome do XML original
            stem_xml = os.path.splitext(os.path.basename(xml_path))[0]
            nome_base = f"DANFSe_NF_{nNFSe}_{stem_xml}"

        pdf_path = os.path.join(pasta_destino, f"{nome_base}.pdf")

        # Se o arquivo já existir (mesma chave processada duas vezes), acrescenta _N
        i = 1
        while os.path.exists(pdf_path):
            pdf_path = os.path.join(pasta_destino, f"{nome_base}_{i}.pdf")
            i += 1

        gerar_pdf_danfse(data, pdf_path)
        return (True, f"OK  | {os.path.basename(xml_path)}  →  {os.path.basename(pdf_path)}",
                pdf_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return (False, f"ERRO | {os.path.basename(xml_path)}  →  {e}", None)


class JanelaProgresso:
    """Janela simples com barra de progresso e log, exibida durante o processamento."""

    def __init__(self, parent, total):
        import tkinter as tk
        from tkinter import ttk
        self.top = tk.Toplevel(parent)
        self.top.title("Gerando DANFSe...")
        self.top.geometry("640x360")
        self.top.resizable(False, False)
        # centraliza na tela
        self.top.update_idletasks()
        w = self.top.winfo_width(); h = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (w // 2)
        y = (self.top.winfo_screenheight() // 2) - (h // 2)
        self.top.geometry(f"+{x}+{y}")

        self.total = total
        self.atual = 0

        # Cabeçalho
        tk.Label(self.top, text="Processando arquivos XML...",
                 font=("Helvetica", 11, "bold")).pack(pady=(10, 4))
        self.lbl_status = tk.Label(self.top, text=f"0 / {total}",
                                   font=("Helvetica", 10))
        self.lbl_status.pack()

        # Barra de progresso
        self.pb = ttk.Progressbar(self.top, orient='horizontal',
                                  mode='determinate', length=600, maximum=total)
        self.pb.pack(pady=8, padx=16)

        # Log
        frame_log = tk.Frame(self.top)
        frame_log.pack(fill='both', expand=True, padx=16, pady=(4, 10))
        scroll = tk.Scrollbar(frame_log)
        scroll.pack(side='right', fill='y')
        self.txt = tk.Text(frame_log, height=12, wrap='none',
                           yscrollcommand=scroll.set,
                           font=("Courier", 8))
        self.txt.pack(side='left', fill='both', expand=True)
        scroll.config(command=self.txt.yview)

        self.top.update()

    def log(self, msg, tag=None):
        self.txt.insert('end', msg + "\n")
        if tag == 'err':
            self.txt.tag_add("err", "end-2l linestart", "end-1l")
            self.txt.tag_config("err", foreground="#c0392b")
        elif tag == 'ok':
            self.txt.tag_add("ok", "end-2l linestart", "end-1l")
            self.txt.tag_config("ok", foreground="#1f7a1f")
        self.txt.see('end')
        self.top.update()

    def avancar(self):
        self.atual += 1
        self.pb['value'] = self.atual
        self.lbl_status.config(text=f"{self.atual} / {self.total}")
        self.top.update()

    def fechar(self):
        self.top.destroy()


def selecionar_arquivos_e_gerar():
    """Abre diálogos para o usuário selecionar vários XMLs e a pasta destino."""
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()

    # 1) Selecionar vários XMLs (askopenfilenames no plural)
    xml_paths = filedialog.askopenfilenames(
        title="Selecione um ou mais arquivos XML da NFS-e "
              "(use Ctrl ou Shift para seleção múltipla)",
        filetypes=[("XML NFS-e", "*.xml *.XML"), ("Todos os arquivos", "*.*")],
    )
    if not xml_paths:
        messagebox.showwarning("DANFSe", "Nenhum arquivo XML selecionado.")
        return

    # Normaliza para lista (retorno do tkinter pode ser tupla)
    xml_paths = list(xml_paths)

    # 2) Selecionar pasta destino
    pasta_destino = filedialog.askdirectory(
        title=f"Selecione a pasta onde salvar os {len(xml_paths)} PDF(s)"
    )
    if not pasta_destino:
        messagebox.showwarning("DANFSe", "Nenhuma pasta destino selecionada.")
        return

    # 3) Janela de progresso + loop
    janela = JanelaProgresso(root, total=len(xml_paths))
    janela.log(f"Pasta destino: {pasta_destino}")
    janela.log(f"Total de arquivos: {len(xml_paths)}")
    janela.log("-" * 70)

    sucessos = 0
    erros = []
    pdfs_gerados = []

    for xml_path in xml_paths:
        ok, msg, pdf_path = _processar_xml_individual(xml_path, pasta_destino)
        janela.log(msg, tag='ok' if ok else 'err')
        janela.avancar()
        if ok:
            sucessos += 1
            pdfs_gerados.append(pdf_path)
        else:
            erros.append(msg)

    janela.log("-" * 70)
    janela.log(f"Finalizado: {sucessos} sucesso(s), {len(erros)} erro(s).")

    # Mensagem final consolidada
    if erros:
        msg_final = (
            f"Processamento concluído.\n\n"
            f"✓ Sucessos: {sucessos}\n"
            f"✗ Erros:    {len(erros)}\n\n"
            f"Pasta destino:\n{pasta_destino}\n\n"
            f"Verifique o log na janela de progresso para detalhes dos erros."
        )
        messagebox.showwarning("DANFSe - Concluído com erros", msg_final)
    else:
        msg_final = (
            f"✓ Todos os {sucessos} PDF(s) foram gerados com sucesso!\n\n"
            f"Pasta destino:\n{pasta_destino}"
        )
        messagebox.showinfo("DANFSe - Sucesso", msg_final)

    # Mantém janela de progresso aberta até o usuário fechá-la
    janela.top.protocol("WM_DELETE_WINDOW", lambda: (janela.fechar(), root.destroy()))
    # Botão de fechar
    btn = tk.Button(janela.top, text="Fechar",
                    command=lambda: (janela.fechar(), root.destroy()))
    btn.pack(pady=(0, 8))
    root.mainloop()


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    # Modo CLI:
    #   python danfse_generator.py <pasta_destino> <xml1> [xml2] [xml3] ...
    # (pasta destino como PRIMEIRO arg, XMLs subsequentes)
    #
    # Compatibilidade: se receber exatamente 2 args e o primeiro terminar em .xml,
    # assume formato antigo: <xml> <pasta_destino>
    args = sys.argv[1:]

    if len(args) >= 2:
        # Windows + Python 3.7+: força stdout/stderr em UTF-8 para evitar
        # UnicodeEncodeError ao imprimir caracteres como '→' no console cp1252.
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

        # Detecta formato antigo (xml, pasta)
        if len(args) == 2 and args[0].lower().endswith(('.xml',)):
            pasta_arg = args[1]
            xmls = [args[0]]
        else:
            # Formato novo: primeiro argumento é a pasta
            pasta_arg = args[0]
            xmls = args[1:]

        if not os.path.isdir(pasta_arg):
            os.makedirs(pasta_arg, exist_ok=True)

        total = len(xmls)
        sucesso = 0
        erro = 0
        print(f"Processando {total} arquivo(s)...")
        print("-" * 70)
        for i, xml in enumerate(xmls, 1):
            ok, msg, pdf_path = _processar_xml_individual(xml, pasta_arg)
            print(f"[{i}/{total}] {msg}")
            if ok:
                sucesso += 1
            else:
                erro += 1
        print("-" * 70)
        print(f"Finalizado: {sucesso} sucesso(s), {erro} erro(s).")
        sys.exit(0 if erro == 0 else 1)
    else:
        # Modo GUI
        selecionar_arquivos_e_gerar()
