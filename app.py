import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

# Regras do Leiaute DIRF 2026 (Anexo Único)
ID_ESTRUTURA = "R6GP3ZA" # [cite: 295]
ANO_REF = "2025"        # [cite: 295]
ANO_CAL = "2024"        # [cite: 295]

def limpar_valor_pgdc(texto):
    """Regra 4: Remove pontos e vírgulas, mantém centavos."""
    if not texto: return "0"
    numeros = re.sub(r'\D', '', texto)
    return numeros if numeros else "0"

def extrair_dados_multi_pdf(arquivos):
    base_dados = []
    for arq in arquivos:
        pdf_bytes = arq.read()
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texto = ""
            for page in pdf.pages:
                txt_pag = page.extract_text()
                if txt_pag and len(txt_pag) > 100:
                    texto += txt_pag + "\n"
                else:
                    # OCR para páginas escaneadas
                    imagens = convert_from_bytes(pdf_bytes, first_page=page.page_number, last_page=page.page_number)
                    for img in imagens:
                        texto += pytesseract.image_to_string(img, lang='por') + "\n"
            
            # Identificação do Mês e Dados
            mes_match = re.search(r"(\d{2})/(\d{4})", texto)
            mes_ref = int(mes_match.group(1)) if mes_match else 0
            
            # Captura por CPF (Âncora Universal) [cite: 91, 332]
            blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto)
            for i in range(1, len(blocos), 2):
                cpf = re.sub(r'\D', '', blocos[i])
                contexto = blocos[i+1]
                # Busca valores de Proventos ou Base Prev [cite: 17, 79, 83]
                valor_match = re.search(r"(?:PROVENTOS|TOTAL DE PROVENTOS|Base Prev.).*?([\d\.,]{4,})", contexto, re.I)
                if valor_match:
                    base_dados.append({
                        'cpf': cpf,
                        'nome': "NOME EXTRAIDO", # Lógica de nome pode ser refinada por linha anterior
                        'mes': mes_ref,
                        'valor': limpar_valor_pgdc(valor_match.group(1))
                    })
    return pd.DataFrame(base_dados)

def gerar_txt_anual(df, r_dados, d_cnpj, d_nome):
    linhas = []
    # 3.1 Dirf - Primeiro registro [cite: 290, 293]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    # 3.2 RESPO - Segundo registro [cite: 297, 300]
    linhas.append(f"RESPO|{re.sub(r'\D','',r_dados['cpf'])}|{r_dados['nome'].upper()}|{r_dados['ddd']}|{r_dados['tel']}||||")
    # 3.4 DECPJ - Terceiro registro [cite: 314, 317]
    linhas.append(f"DECPJ|{re.sub(r'\D','',d_cnpj)}|{d_nome.upper()}|2|{re.sub(r'\D','',r_dados['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 IDREC - Código de Receita [cite: 325, 329]
    linhas.append(f"IDREC|0561|")

    # Consolidação Anual por Beneficiário [cite: 430]
    for cpf, group in df.groupby('cpf'):
        # 3.6 BPFDEC [cite: 330, 335]
        linhas.append(f"BPFDEC|{cpf}|{group['nome'].iloc[0]}||N|N|")
        # 3.19 RTRT - 14 colunas (Jan a Dez + 13º) [cite: 427, 437, 549]
        valores = [""] * 13
        for _, row in group.iterrows():
            if 1 <= row['mes'] <= 13:
                valores[row['mes']-1] = row['valor']
        # Regra 6: Delimitador Pipe 
        linhas.append(f"RTRT|{'|'.join(valores)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 657, 660]
    return "\n".join(linhas)

# Interface
st.set_page_config(page_title="Consolidador Anual DIRF", layout="wide")
st.title("⚖️ Consolidador Anual: JURIPREV / FUNPREVCAP")

with st.sidebar:
    st.header("Dados do Responsável")
    r_nome = st.text_input("Nome")
    r_cpf = st.text_input("CPF")
    r_ddd = st.text_input("DDD")
    r_tel = st.text_input("Telefone")

arquivos = st.file_uploader("Selecione os 12 meses + 13º (PDFs)", type="pdf", accept_multiple_files=True)

if arquivos and r_nome:
    if st.button("🚀 PROCESSAR E GERAR ARQUIVO ANUAL"):
        df_consolidado = extrair_dados_multi_pdf(arquivos)
        if not df_consolidado.empty:
            st.write("### Conferência dos Valores Consolidados")
            st.dataframe(df_consolidado)
            
            txt = gerar_txt_anual(df_consolidado, {'nome':r_nome, 'cpf':r_cpf, 'ddd':r_ddd, 'tel':r_tel}, "06104166000134", "ENTIDADE DECLARANTE")
            st.download_button("📥 Baixar Arquivo Único (DIRF)", txt.encode('latin-1'), "DIRF_ANUAL_CONSOLIDADA.txt")