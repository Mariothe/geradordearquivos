import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from PIL import Image
import pytesseract # Requer Tesseract instalado no servidor

# Configurações do Leiaute Dirf 2026 (Anexo Único)
ID_ESTRUTURA = "R6GP3ZA" # [cite: 295]
ANO_REF = "2025"        # [cite: 295]
ANO_CAL = "2024"        # [cite: 295]

def limpar_valor_pgdc(texto):
    """Regra 4: Transforma 'R$ 3.036,00' em '303600'[cite: 91]."""
    if not texto: return "0"
    # Remove tudo que não é dígito
    numeros = re.sub(r'\D', '', texto)
    return numeros if numeros else "0"

def extrair_texto_ocr(pdf_bytes):
    """Lê PDFs de texto ou escaneados (OCR)."""
    texto_final = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            # Tenta extrair texto normal
            temp = page.extract_text()
            if temp and len(temp.strip()) > 50:
                texto_final += temp + "\n"
            else:
                # Se estiver vazio ou for imagem, usa OCR
                img = page.to_image(resolution=300).original
                texto_final += pytesseract.image_to_string(img, lang='por') + "\n"
    return texto_final

def extrair_dados_universal(texto):
    """Mapeia Nome, CPF e Valores de qualquer entidade[cite: 91, 151, 153]."""
    dados = []
    # Identifica Mês/Ano (ex: 08/2025) [cite: 61, 91]
    data_match = re.search(r"(\d{2})/(\d{4})", texto)
    mes_ref = int(data_match.group(1)) if data_match else 1
    
    # Divide por blocos de CPF (âncora universal) [cite: 91, 302, 335]
    blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto)
    for i in range(1, len(blocos), 2):
        cpf = re.sub(r'\D', '', blocos[i]) # [cite: 91]
        contexto = blocos[i+1]
        
        # Busca 'Proventos' ou 'Líquido' na tabela [cite: 79, 83]
        valor_match = re.search(r"(?:PROVENTOS|TOTAL DE PROVENTOS|Base Prev.).*?([\d\.,]{4,})", contexto, re.I)
        
        if valor_match:
            dados.append({
                'cpf': cpf,
                'mes': mes_ref,
                'valor': limpar_valor_pgdc(valor_match.group(1))
            })
    return dados

def gerar_dirf_completo(df, r_dados, d_cnpj, d_nome):
    """Monta o arquivo respeitando a hierarquia[cite: 290, 297, 314, 325, 427, 657]."""
    linhas = []
    # 3.1 Dirf (1º Registro) [cite: 290]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    # 3.2 RESPO (2º Registro) [cite: 297, 303, 304]
    linhas.append(f"RESPO|{re.sub(r'\D','',r_dados['cpf'])}|{r_dados['nome'].upper()}|{r_dados['ddd']}|{r_dados['tel']}||||")
    # 3.4 DECPJ (3º Registro) [cite: 314, 320, 321]
    linhas.append(f"DECPJ|{re.sub(r'\D','',d_cnpj)}|{d_nome.upper()}|1|{re.sub(r'\D','',r_dados['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 IDREC (Obrigatório) [cite: 325, 329]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        # 3.6 BPFDEC (Beneficiário) [cite: 330, 335]
        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_{cpf}||N|N|")
        # 3.19 RTRT (Consolidação 12 meses) [cite: 427, 437, 479, 543, 549]
        valores = [""] * 13 # Jan a Dez + 13º [cite: 549]
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            valores[idx] = row['valor']
        # Regra 6: Delimitador Pipe [cite: 91]
        linhas.append(f"RTRT|{'|'.join(valores)}|")

    # 3.36 FIMDirf (Último Registro) [cite: 657, 662]
    linhas.append("FIMDirf|")
    return "\n".join(linhas)

# Interface Web Streamlit
st.title("🏦 Consolidador DIRF 2026 (PDF e Escaneados)")
st.sidebar.header("Responsável (RESPO) [cite: 297]")
r_nome = st.sidebar.text_input("Nome")
r_cpf = st.sidebar.text_input("CPF")
r_ddd = st.sidebar.text_input("DDD")
r_tel = st.sidebar.text_input("Telefone")

# Upload de múltiplas páginas/arquivos
arquivos = st.file_uploader("Suba as folhas de pagamento (pode ser vários PDFs)", type="pdf", accept_multiple_files=True)

if arquivos and r_nome:
    todos_dados = []
    for f in arquivos:
        texto = extrair_texto_ocr(f.read())
        todos_dados.extend(extrair_dados_universal(texto))
    
    if todos_dados:
        df = pd.DataFrame(todos_dados)
        st.write("### Conferência dos 12 meses (Consolidado)")
        st.table(df.groupby(['cpf', 'mes']).sum()) # Mostra soma por mês para conferência [cite: 430]
        
        txt = gerar_dirf_completo(df, {'nome':r_nome, 'cpf':r_cpf, 'ddd':r_ddd, 'tel':r_tel}, "06104166000134", "FUNPREVCAP")
        st.download_button("📥 Baixar Arquivo PGD-C Consolidado", txt.encode('latin-1'), "DIRF_CONSOLIDADA.txt")