import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

ID_ESTRUTURA = "R6GP3ZA"
ANO_REF = "2025"
ANO_CAL = "2024"

# --------------------------------------------------
# FUNÇÕES DE LIMPEZA
# --------------------------------------------------

def limpar_valor(texto):
    if not texto:
        return 0
    return int(re.sub(r"\D", "", texto))


# --------------------------------------------------
# EXTRAÇÃO TEXTO PDF
# --------------------------------------------------

def extrair_texto(pdf_bytes):
    texto = ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t and len(t) > 40:
                texto += t + "\n"
            else:
                imagens = convert_from_bytes(pdf_bytes,
                                              first_page=page.page_number,
                                              last_page=page.page_number)
                for img in imagens:
                    texto += pytesseract.image_to_string(img, lang="por") + "\n"
    return texto


# --------------------------------------------------
# EXTRAÇÃO DE DADOS
# --------------------------------------------------

def extrair_mes(texto):
    m = re.search(r"M[eê]s/Ano\s+(\d{2})/(\d{4})", texto)
    return int(m.group(1)) if m else None


def extrair_blocos(texto):
    blocos = re.split(r"CPF[:\s]*(\d{11})", texto)
    resultado = []
    for i in range(1, len(blocos)-1, 2):
        resultado.append((blocos[i], blocos[i+1]))
    return resultado


def extrair_valores(contexto):

    base = re.search(r"(?:Base\s*Prev\.?|Proventos)[\s\r\n]+([\d\.,]+)", contexto, re.I)
    irrf = re.search(r"IRRF.*?([\d\.,]+)$", contexto, re.M)
    prev = re.search(r"PREVID[ÊE]NCIA.*?([\d\.,]+)$", contexto, re.M)
    decimo = re.search(r"13", contexto)

    return {
        "base": limpar_valor(base.group(1)) if base else 0,
        "irrf": limpar_valor(irrf.group(1)) if irrf else 0,
        "prev": limpar_valor(prev.group(1)) if prev else 0,
        "decimo": True if decimo else False
    }


def extrair_dados(arquivos):

    dados = []

    for arq in arquivos:
        texto = extrair_texto(arq.read())
        mes = extrair_mes(texto)
        if not mes:
            continue

        for cpf, ctx in extrair_blocos(texto):
            valores = extrair_valores(ctx)

            dados.append({
                "cpf": cpf,
                "mes": mes,
                "base": valores["base"],
                "irrf": valores["irrf"],
                "prev": valores["prev"],
                "decimo": valores["decimo"]
            })

    df = pd.DataFrame(dados)

    if not df.empty:
        df = df.groupby(["cpf","mes"], as_index=False).sum()

    return df


# --------------------------------------------------
# GERAÇÃO DIRF COMPATÍVEL COM PGD
# --------------------------------------------------

def gerar_dirf(df, responsavel, cnpj, nome):

    linhas = []

    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    linhas.append(f"RESPO|{responsavel['cpf']}|{responsavel['nome']}|{responsavel['ddd']}|{responsavel['tel']}||||")
    linhas.append(f"DECPJ|{cnpj}|{nome}|1|{responsavel['cpf']}|N|N|N|N|N|N|N|N||")
    linhas.append("IDREC|0561|")

    for cpf, grupo in df.groupby("cpf"):

        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_IDENTIFICADO||N|N|")

        rend = [""]*13
        irrf = [""]*13
        prev = [""]*13
        dec13 = ""

        for _, r in grupo.iterrows():
            idx = r["mes"]-1
            rend[idx] = str(r["base"])
            irrf[idx] = str(r["irrf"])
            prev[idx] = str(r["prev"])

            if r["decimo"]:
                dec13 = str(r["base"])

        linhas.append(f"RTRT|{'|'.join(rend)}|")
        linhas.append(f"RTIRF|{'|'.join(irrf)}|")
        linhas.append(f"RTPS|{'|'.join(prev)}|")

        if dec13:
            linhas.append(f"RT13|{dec13}|")

    linhas.append("FIMDirf|")

    return "\n".join(linhas)


# --------------------------------------------------
# INTERFACE
# --------------------------------------------------

st.set_page_config(layout="wide")
st.title("Consolidador DIRF e Informes de Rendimentos")

with st.sidebar:
    nome = st.text_input("Responsável", "MARIO FLAVIO PEREIRA")
    cpf = st.text_input("CPF", "84598000325")
    ddd = st.text_input("DDD", "86")
    tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader("Envie os PDFs mensais", type="pdf", accept_multiple_files=True)

if arquivos and st.button("Gerar DIRF"):
    df = extrair_dados(arquivos)

    if df.empty:
        st.error("Nenhum dado encontrado.")
    else:
        st.dataframe(df)

        txt = gerar_dirf(
            df,
            {"nome":nome,"cpf":cpf,"ddd":ddd,"tel":tel},
            "06104166000134",
            "FUNPREVCAP"
        )

        st.download_button("Baixar Arquivo DIRF", txt.encode("latin-1"), "DIRF.txt")