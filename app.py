import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

# Regras do Leiaute DIRF 2026 (Anexo Único)
ID_ESTRUTURA = "R6GP3ZA" # [cite: 295]
ANO_REF = "2025"         # [cite: 295]
ANO_CAL = "2024"         # [cite: 295]

def limpar_valor_pgdc(texto):
    """Regra 4: Transforma 'R$ 1.384,00' em '138400'."""
    if not texto: return "0"
    # Remove todos os caracteres não numéricos [cite: 91]
    numeros = re.sub(r'\D', '', texto)
    return numeros if numeros else "0"

def extrair_dados_multi_pdf(arquivos):
    base_dados = []
    for arq in arquivos:
        pdf_bytes = arq.read()
        texto = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                txt_pag = page.extract_text()
                # Verifica se é PDF de texto ou imagem
                if txt_pag and len(txt_pag) > 100:
                    texto += txt_pag + "\n"
                else:
                    imagens = convert_from_bytes(pdf_bytes, first_page=page.page_number, last_page=page.page_number)
                    for img in imagens:
                        texto += pytesseract.image_to_string(img, lang='por') + "\n"
        
        # Identificação do Mês/Ano (ex: 03/2025)
        mes_match = re.search(r"(\d{2})/(\d{4})", texto)
        mes_ref = int(mes_match.group(1)) if mes_match else 0
        
        # Captura por blocos de CPF (Regra 3)
        blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto)
        for i in range(1, len(blocos), 2):
            cpf = re.sub(r'\D', '', blocos[i]) # [cite: 91]
            contexto = blocos[i+1]
            # Busca valores de Proventos/Base Prev (Regra 4)
            valor_match = re.search(r"(?:PROVENTOS|TOTAL DE PROVENTOS|Base Prev.).*?([\d\.,]{4,})", contexto, re.I)
            if valor_match:
                base_dados.append({
                    'cpf': cpf,
                    'mes': mes_ref,
                    'valor': limpar_valor_pgdc(valor_match.group(1))
                })
    return pd.DataFrame(base_dados)

def gerar_txt_anual(df, r_dados, d_cnpj, d_nome):
    linhas = []
    # 3.1 Dirf - Primeiro registro obrigatório [cite: 293]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|") # [cite: 91]
    # 3.2 RESPO - Segundo registro obrigatório [cite: 300]
    linhas.append(f"RESPO|{re.sub(r'\D','',r_dados['cpf'])}|{r_dados['nome'].upper()}|{r_dados['ddd']}|{r_dados['tel']}||||")
    # 3.4 DECPJ - Terceiro registro [cite: 317]
    linhas.append(f"DECPJ|{re.sub(r'\D','',d_cnpj)}|{d_nome.upper()}|1|{re.sub(r'\D','',r_dados['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 IDREC - Código de Receita crescente [cite: 327]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        # 3.6 BPFDEC - Beneficiário [cite: 332]
        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_{cpf}||N|N|")
        # 3.19 RTRT - Consolidação (12 meses + 13º) [cite: 427, 430]
        valores = [""] * 13
        for _, row in group.iterrows():
            if 1 <= row['mes'] <= 13:
                valores[row['mes']-1] = row['valor']
        # Delimitador pipe ao final de cada registro [cite: 91]
        linhas.append(f"RTRT|{'|'.join(valores)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 660]
    return "\n".join(linhas)

# Interface Streamlit
st.title("⚖️ Consolidador Anual PGD-C")
with st.sidebar:
    st.header("Dados do Responsável")
    r_nome = st.text_input("Nome", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader("Selecione os PDFs (Jan a Dez + 13º)", type="pdf", accept_multiple_files=True)

if arquivos and r_nome:
    if st.button("🚀 GERAR ARQUIVO CONSOLIDADO"):
        df = extrair_dados_multi_pdf(arquivos)
        if not df.empty:
            st.table(df) # Conferência visual
            txt = gerar_txt_anual(df, {'nome':r_nome, 'cpf':r_cpf, 'ddd':r_ddd, 'tel':r_tel}, "25316695000146", "JURIPREV TECNOLOGIAS")
            st.download_button("📥 Baixar Arquivo Anual", txt.encode('latin-1'), "DIRF_CONSOLIDADA.txt")