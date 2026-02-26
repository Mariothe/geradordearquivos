import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

# Configurações do Leiaute Dirf 2026 (Anexo Único)
ID_ESTRUTURA = "R6GP3ZA" # [cite: 295]
ANO_REF = "2025"         # [cite: 295]
ANO_CAL = "2024"         # [cite: 295]

def limpar_valor_pgdc(texto):
    """Regra 4: Transforma valores monetários em string numérica de centavos."""
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
                    if txt and len(txt) > 100:
                        texto_acumulado += txt + "\n"
                    else:
                        # Processa como imagem se o texto falhar (OCR)
                        imagens = convert_from_bytes(pdf_bytes, first_page=page.page_number, last_page=page.page_number)
                        for img in imagens:
                            texto_acumulado += pytesseract.image_to_string(img, lang='por') + "\n"
        except Exception as e:
            st.warning(f"Erro ao ler {arq.name}. Verifique se poppler e tesseract estão instalados.")
            continue

        # Identifica Mês/Ano (Ex: 03/2025)
        mes_match = re.search(r"(\d{2})/(\d{4})", texto_acumulado)
        mes_ref = int(mes_match.group(1)) if mes_match else 0
        
        # Captura por blocos de CPF (Regra 3) 
        blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto_acumulado)
        for i in range(1, len(blocos), 2):
            cpf = re.sub(r'\D', '', blocos[i])
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

def gerar_txt_final(df, r_dados, d_cnpj, d_nome):
    linhas = []
    # 3.1 Dirf - Obrigatório, 1º registro [cite: 290, 293]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    # 3.2 RESPO - Obrigatório, 2º registro [cite: 297, 300]
    linhas.append(f"RESPO|{re.sub(r'\D','',r_dados['cpf'])}|{r_dados['nome'].upper()}|{r_dados['ddd']}|{r_dados['tel']}||||")
    # 3.4 DECPJ - Identificação do Declarante [cite: 314, 317]
    linhas.append(f"DECPJ|{re.sub(r'\D','',d_cnpj)}|{d_nome.upper()}|1|{re.sub(r'\D','',r_dados['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 IDREC - Código de Receita crescente [cite: 325, 327]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        # 3.6 BPFDEC - Beneficiário Pessoa Física [cite: 330, 332]
        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_IDENTIFICADO||N|N|")
        # 3.19 RTRT - Consolidação Anual (14 campos) 
        valores = [""] * 13 
        for _, row in group.iterrows():
            if 1 <= row['mes'] <= 13:
                valores[row['mes']-1] = row['valor']
        # Regra 6: Delimitador Pipe ao final de cada registro 
        linhas.append(f"RTRT|{'|'.join(valores)}|")

    linhas.append("FIMDirf|") # 3.36 Término da declaração [cite: 657, 660]
    return "\n".join(linhas)

# Interface
st.set_page_config(page_title="Consolidador DIRF Anual", layout="wide")
st.title("⚖️ Consolidador Anual PGD-C")

with st.sidebar:
    st.header("Dados do Responsável")
    r_nome = st.text_input("Nome", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF (Somente números)", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader("Suba as folhas (Mínimo 13 para ano completo)", type="pdf", accept_multiple_files=True)

if arquivos and r_nome and r_cpf:
    if st.button("🚀 CONSOLIDAR E GERAR ARQUIVO ANUAL"):
        df = extrair_dados_consolidado(arquivos)
        if not df.empty:
            st.success(f"Dados consolidados de {len(df['cpf'].unique())} beneficiários.")
            st.write("### Conferência de Valores por Mês")
            st.table(df) # Exibição para conferência
            
            txt_final = gerar_txt_final(df, {'nome':r_nome, 'cpf':r_cpf, 'ddd':r_ddd, 'tel':r_tel}, "25316695000146", "JURIPREV TECNOLOGIAS")
            st.download_button("📥 Baixar Arquivo Consolidado (.TXT)", txt_final.encode('latin-1'), "DIRF_CONSOLIDADA_ANUAL.txt")