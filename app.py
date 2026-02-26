import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import pytesseract
from pdf2image import convert_from_bytes

# ==============================
# CONFIGURAÇÕES DIRF
# ==============================

ID_ESTRUTURA = "R6GP3ZA"
ANO_REF = "2025"
ANO_CAL = "2024"

# ==============================
# UTILITÁRIOS
# ==============================

def limpar_valor_pgdc(texto):
    if not texto:
        return ""
    numeros = re.sub(r"\D", "", texto)
    return numeros if numeros else ""


def extrair_texto_pdf(pdf_bytes):
    texto_final = ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()

            if txt and len(txt.strip()) > 50:
                texto_final += txt + "\n"
            else:
                imagens = convert_from_bytes(
                    pdf_bytes,
                    first_page=page.page_number,
                    last_page=page.page_number
                )
                for img in imagens:
                    texto_final += pytesseract.image_to_string(
                        img, lang="por"
                    ) + "\n"

    return texto_final


def extrair_mes_referencia(texto):
    match = re.search(r"M[eê]s/Ano\s+(\d{2})/(\d{4})", texto)
    if match:
        return int(match.group(1))
    return None


def extrair_blocos_por_cpf(texto):
    padrao = r"(?:CPF[:\s]*)(\d{11})"
    blocos = re.split(padrao, texto)

    resultado = []

    for i in range(1, len(blocos) - 1, 2):
        cpf = blocos[i]
        contexto = blocos[i + 1]
        resultado.append((cpf, contexto))

    return resultado


def extrair_valor_base(contexto):
    padrao = r"(?:Base\s*Prev\.?|Proventos)[\s\r\n]+([\d\.,]+)"
    match = re.search(padrao, contexto, re.I)

    if match:
        return limpar_valor_pgdc(match.group(1))

    return None


# ==============================
# EXTRAÇÃO PRINCIPAL
# ==============================

def extrair_dados_consolidado(arquivos):

    base_dados = []
    inconsistencias = []
    total_pdfs = 0

    for arq in arquivos:
        total_pdfs += 1
        pdf_bytes = arq.read()
        texto = extrair_texto_pdf(pdf_bytes)

        mes = extrair_mes_referencia(texto)
        if not mes:
            inconsistencias.append(f"{arq.name}: Mês não identificado.")
            continue

        blocos = extrair_blocos_por_cpf(texto)

        if not blocos:
            inconsistencias.append(f"{arq.name}: Nenhum CPF encontrado.")

        for cpf, contexto in blocos:
            valor = extrair_valor_base(contexto)

            if not valor:
                inconsistencias.append(
                    f"{arq.name}: CPF {cpf} sem valor Base Prev/Proventos."
                )
                continue

            base_dados.append({
                "cpf": cpf,
                "mes": mes,
                "valor": int(valor)
            })

    df = pd.DataFrame(base_dados)

    # Consolidação por CPF + Mês (soma automática)
    if not df.empty:
        df = df.groupby(["cpf", "mes"], as_index=False)["valor"].sum()

    return df, inconsistencias, total_pdfs


# ==============================
# VALIDAÇÃO TXT
# ==============================

def validar_txt(linhas):

    erros = []

    if not linhas[0].startswith("Dirf|"):
        erros.append("Registro Dirf ausente.")

    if not any(l.startswith("IDREC|") for l in linhas):
        erros.append("Registro IDREC ausente.")

    bpfdec = sum(1 for l in linhas if l.startswith("BPFDEC|"))
    rtrt = sum(1 for l in linhas if l.startswith("RTRT|"))

    if bpfdec != rtrt:
        erros.append("Quantidade de BPFDEC diferente de RTRT.")

    if not linhas[-1].startswith("FIMDirf|"):
        erros.append("Registro FIMDirf ausente.")

    return erros


# ==============================
# GERAÇÃO TXT DIRF
# ==============================

def gerar_txt_consolidado(df, r_dados, d_cnpj, d_nome):

    linhas = []

    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")

    linhas.append(
        f"RESPO|{re.sub(r'\\D','',r_dados['cpf'])}|"
        f"{r_dados['nome'].upper()}|"
        f"{r_dados['ddd']}|{r_dados['tel']}||||"
    )

    linhas.append(
        f"DECPJ|{re.sub(r'\\D','',d_cnpj)}|"
        f"{d_nome.upper()}|1|"
        f"{re.sub(r'\\D','',r_dados['cpf'])}|"
        f"N|N|N|N|N|N|N|N||"
    )

    linhas.append("IDREC|0561|")

    total_geral = 0

    for cpf, group in df.groupby("cpf"):

        linhas.append(f"BPFDEC|{cpf}|BENEFICIARIO_IDENTIFICADO||N|N|")

        valores = [""] * 13

        for _, row in group.iterrows():
            if 1 <= row["mes"] <= 13:
                valores[row["mes"] - 1] = str(row["valor"])
                total_geral += row["valor"]

        linhas.append(f"RTRT|{'|'.join(valores)}|")

    linhas.append("FIMDirf|")

    erros = validar_txt(linhas)

    return "\n".join(linhas), erros, total_geral


# ==============================
# INTERFACE
# ==============================

st.set_page_config(page_title="Consolidador DIRF Auditoria", layout="wide")
st.title("⚖️ Consolidador DIRF - Nível Auditoria")

with st.sidebar:
    st.header("Responsável")
    r_nome = st.text_input("Nome", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

arquivos = st.file_uploader(
    "Suba todos os meses (PDFs)",
    type="pdf",
    accept_multiple_files=True
)

if arquivos and r_nome:
    if st.button("🚀 GERAR ARQUIVO CONSOLIDADO"):

        df, inconsistencias, total_pdfs = extrair_dados_consolidado(arquivos)

        st.subheader("📊 Relatório Técnico")

        st.write(f"PDFs processados: {total_pdfs}")
        st.write(f"CPFs encontrados: {df['cpf'].nunique() if not df.empty else 0}")

        if not df.empty:
            st.dataframe(df.sort_values(["cpf", "mes"]))

            txt, erros_txt, total_geral = gerar_txt_consolidado(
                df,
                {
                    "nome": r_nome,
                    "cpf": r_cpf,
                    "ddd": r_ddd,
                    "tel": r_tel
                },
                "25316695000146",
                "ENTIDADE DECLARANTE"
            )

            st.write(f"Total anual consolidado (centavos): {total_geral}")

            if inconsistencias:
                st.warning("⚠ Inconsistências Encontradas:")
                for inc in inconsistencias:
                    st.write("-", inc)

            if erros_txt:
                st.error("❌ Erro estrutural no TXT:")
                for e in erros_txt:
                    st.write("-", e)
            else:
                st.success("TXT validado estruturalmente.")
                st.download_button(
                    "📥 Baixar TXT DIRF",
                    txt.encode("latin-1"),
                    "DIRF_CONSOLIDADA.txt"
                )

        else:
            st.error("Nenhum dado válido encontrado.")