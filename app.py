import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import os
import zipfile
from decimal import Decimal

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

# =========================================================
# CONFIGURAÇÃO
# =========================================================

ANO_REF = "2025"
ANO_CAL = "2024"
CNPJ_FONTE = "06104166000134"
NOME_FONTE = "FUNPREVCAP"
ID_ESTRUTURA = "R6GP3ZA"

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def normalizar_valor(valor_str):
    """
    Converte valores brasileiros:
    1.384,00 -> 138400 (centavos)
    """
    if not valor_str:
        return 0

    valor_str = valor_str.strip()
    valor_str = valor_str.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(valor_str)
        return int(valor * 100)
    except:
        return 0


def extrair_texto(pdf_bytes):
    texto_total = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texto_total += t + "\n"
    return texto_total


def extrair_mes(texto):
    m = re.search(r"M[eê]s/Ano\s+(\d{2})/(\d{4})", texto)
    return int(m.group(1)) if m else None


def extrair_blocos_por_cpf(texto):
    partes = re.split(r"CPF[:\s]*(\d{11})", texto)
    blocos = []
    for i in range(1, len(partes)-1, 2):
        blocos.append((partes[i], partes[i+1]))
    return blocos


def extrair_valores(contexto):

    base = re.search(r"Proventos\s+([\d\.,]+)", contexto)
    irrf = re.search(r"IRRF.*?([\d\.,]+)", contexto)
    prev = re.search(r"PREVID[ÊE]NCIA.*?([\d\.,]+)", contexto)

    return {
        "base": normalizar_valor(base.group(1)) if base else 0,
        "irrf": normalizar_valor(irrf.group(1)) if irrf else 0,
        "prev": normalizar_valor(prev.group(1)) if prev else 0
    }


# =========================================================
# CONSOLIDAÇÃO
# =========================================================

def processar_pdfs(arquivos):

    dados = []

    for arquivo in arquivos:
        texto = extrair_texto(arquivo.read())
        mes = extrair_mes(texto)
        if not mes:
            continue

        blocos = extrair_blocos_por_cpf(texto)

        for cpf, contexto in blocos:
            valores = extrair_valores(contexto)

            dados.append({
                "cpf": cpf,
                "mes": mes,
                "base": valores["base"],
                "irrf": valores["irrf"],
                "prev": valores["prev"]
            })

    df = pd.DataFrame(dados)

    if not df.empty:
        df = df.groupby(["cpf","mes"], as_index=False).sum()

    return df


# =========================================================
# GERAÇÃO DIRF
# =========================================================

def gerar_dirf(df, responsavel):

    linhas = []

    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    linhas.append(f"RESPO|{responsavel['cpf']}|{responsavel['nome']}|{responsavel['ddd']}|{responsavel['tel']}||||")
    linhas.append(f"DECPJ|{CNPJ_FONTE}|{NOME_FONTE}|1|{responsavel['cpf']}|N|N|N|N|N|N|N|N||")
    linhas.append("IDREC|0561|")

    for cpf, grupo in df.groupby("cpf"):

        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_IDENTIFICADO||N|N|")

        rend = [""]*13
        irrf = [""]*13
        prev = [""]*13

        for _, r in grupo.iterrows():
            idx = r["mes"]-1
            rend[idx] = str(r["base"])
            irrf[idx] = str(r["irrf"])
            prev[idx] = str(r["prev"])

        linhas.append(f"RTRT|{'|'.join(rend)}|")
        linhas.append(f"RTIRF|{'|'.join(irrf)}|")
        linhas.append(f"RTPS|{'|'.join(prev)}|")

    linhas.append("FIMDirf|")

    return "\n".join(linhas)


# =========================================================
# INFORMES PDF
# =========================================================

def gerar_informes(df):

    pasta = "informes_temp"
    os.makedirs(pasta, exist_ok=True)
    styles = getSampleStyleSheet()
    arquivos = []

    for cpf, grupo in df.groupby("cpf"):

        total_base = grupo["base"].sum() / 100
        total_irrf = grupo["irrf"].sum() / 100
        total_prev = grupo["prev"].sum() / 100

        caminho = f"{pasta}/Informe_{cpf}.pdf"

        doc = SimpleDocTemplate(caminho, topMargin=20*mm)
        elementos = []

        elementos.append(Paragraph("<b>INFORME DE RENDIMENTOS</b>", styles["Heading2"]))
        elementos.append(Spacer(1,12))

        elementos.append(Paragraph(f"<b>Fonte Pagadora:</b> {NOME_FONTE}", styles["Normal"]))
        elementos.append(Paragraph(f"<b>CNPJ:</b> {CNPJ_FONTE}", styles["Normal"]))
        elementos.append(Spacer(1,12))

        elementos.append(Paragraph(f"<b>CPF:</b> {cpf}", styles["Normal"]))
        elementos.append(Spacer(1,12))

        elementos.append(Paragraph(f"Rendimentos Tributáveis: R$ {total_base:,.2f}", styles["Normal"]))
        elementos.append(Paragraph(f"Previdência Oficial: R$ {total_prev:,.2f}", styles["Normal"]))
        elementos.append(Paragraph(f"IRRF Retido: R$ {total_irrf:,.2f}", styles["Normal"]))

        doc.build(elementos)
        arquivos.append(caminho)

    zip_path = "Informes_Rendimentos.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for arq in arquivos:
            zipf.write(arq, os.path.basename(arq))

    return zip_path


# =========================================================
# INTERFACE STREAMLIT
# =========================================================

st.set_page_config(layout="wide")
st.title("Sistema DIRF + Informes de Rendimentos")

with st.sidebar:
    nome_resp = st.text_input("Responsável", "MARIO FLAVIO PEREIRA")
    cpf_resp = st.text_input("CPF", "84598000325")
    ddd = st.text_input("DDD", "86")
    tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader("Envie os PDFs mensais", type="pdf", accept_multiple_files=True)

if arquivos and st.button("Processar Arquivos"):

    df = processar_pdfs(arquivos)

    if df.empty:
        st.error("Nenhum dado encontrado.")
    else:
        st.success("Dados extraídos com sucesso.")
        st.dataframe(df)

        responsavel = {
            "nome": nome_resp,
            "cpf": cpf_resp,
            "ddd": ddd,
            "tel": tel
        }

        dirf_txt = gerar_dirf(df, responsavel)

        st.download_button(
            "Baixar Arquivo DIRF",
            dirf_txt.encode("latin-1"),
            "DIRF.txt"
        )

        zip_path = gerar_informes(df)

        st.download_button(
            "Baixar Informes de Rendimentos (PDF)",
            open(zip_path, "rb"),
            "Informes_Rendimentos.zip"
        )