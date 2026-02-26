import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

# Configurações do Leiaute Dirf 2026
ID_ESTRUTURA = "R6GP3ZA" # [cite: 295]
ANO_REF = "2025"         # [cite: 295]
ANO_CAL = "2024"         # [cite: 295]

def limpar_valor_pgdc(texto):
    """Regra 4: Converte R$ 1.384,00 em 138400[cite: 91]."""
    if not texto: return "0"
    numeros = re.sub(r'\D', '', texto)
    return numeros if numeros else "0"

def extrair_dados_consolidado(arquivos):
    base_dados = []
    for arq in arquivos:
        pdf_bytes = arq.read()
        texto_acumulado = ""
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text()
                    if txt and len(txt) > 50:
                        texto_acumulado += txt + "\n"
                    else:
                        # OCR para PDFs escaneados
                        imagens = convert_from_bytes(pdf_bytes, first_page=page.page_number, last_page=page.page_number)
                        for img in imagens:
                            texto_acumulado += pytesseract.image_to_string(img, lang='por') + "\n"
        except: continue

        # Identifica Mês (Ex: 03/2025) [cite: 9, 61]
        mes_match = re.search(r"(\d{2})/(\d{4})", texto_acumulado)
        mes_ref = int(mes_match.group(1)) if mes_match else 1
        
        # Separação por CPF (Regra 3) [cite: 91]
        blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto_acumulado)
        for i in range(1, len(blocos), 2):
            cpf = re.sub(r'\D', '', blocos[i])
            contexto = blocos[i+1]
            # Busca valores na coluna Proventos ou Base Prev [cite: 17, 79]
            valor_match = re.search(r"(?:PROVENTOS|TOTAL DE PROVENTOS|Base Prev.).*?([\d\.,]{4,})", contexto, re.I)
            if valor_match:
                base_dados.append({
                    'cpf': cpf,
                    'mes': mes_ref,
                    'valor': limpar_valor_pgdc(valor_match.group(1))
                })
    return pd.DataFrame(base_dados)

def gerar_txt_consolidado(df, r_dados, d_cnpj, d_nome):
    linhas = []
    # 3.1 Dirf [cite: 290]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    # 3.2 RESPO [cite: 297]
    linhas.append(f"RESPO|{re.sub(r'\D','',r_dados['cpf'])}|{r_dados['nome'].upper()}|{r_dados['ddd']}|{r_dados['tel']}||||")
    # 3.4 DECPJ [cite: 314]
    linhas.append(f"DECPJ|{re.sub(r'\D','',d_cnpj)}|{d_nome.upper()}|1|{re.sub(r'\D','',r_dados['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 IDREC [cite: 325]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        # 3.6 BPFDEC [cite: 330]
        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_IDENTIFICADO||N|N|")
        # 3.19 RTRT (13 campos de valores) [cite: 427, 479]
        valores = [""] * 13 
        for _, row in group.iterrows():
            if 1 <= row['mes'] <= 13:
                valores[row['mes']-1] = row['valor']
        # Regra 6: Delimitador Pipe [cite: 91]
        linhas.append(f"RTRT|{'|'.join(valores)}|")

    linhas.append("FIMDirf|") # 3.36 [cite: 657]
    return "\n".join(linhas)

# Interface
st.set_page_config(page_title="Consolidador DIRF", layout="wide")
st.title("⚖️ Consolidador Anual PGD-C")

with st.sidebar:
    st.header("Responsável")
    r_nome = st.text_input("Nome", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader("Suba todos os meses (PDFs)", type="pdf", accept_multiple_files=True)

if arquivos and r_nome:
    if st.button("🚀 GERAR ARQUIVO CONSOLIDADO"):
        df = extrair_dados_consolidado(arquivos)
        if not df.empty:
            st.success(f"Sucesso! {len(df['cpf'].unique())} CPFs encontrados.")
            st.table(df.sort_values(by=['cpf', 'mes'])) # Conferência visual
            
            txt = gerar_txt_consolidado(df, {'nome':r_nome, 'cpf':r_cpf, 'ddd':r_ddd, 'tel':r_tel}, "25316695000146", "ENTIDADE DECLARANTE")
            st.download_button("📥 Baixar TXT Anual", txt.encode('latin-1'), "DIRF_CONSOLIDADA.txt")