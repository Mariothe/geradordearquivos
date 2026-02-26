import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Parâmetros Obrigatórios - Registro 3.1 [cite: 295]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def formatar_valor_tecnico(texto):
    """
    Regra 4: Campos numéricos de valores com 2 decimais.
    Remove pontos de milhar e símbolos, tratando os últimos 2 dígitos como centavos.
    """
    if not texto: return "0"
    # Mantém apenas dígitos e a última vírgula se existir
    limpo = re.sub(r'[^\d,]', '', texto)
    if ',' in limpo:
        partes = limpo.split(',')
        # Une a parte inteira com os 2 primeiros dígitos decimais
        return f"{partes[0]}{partes[1].ljust(2, '0')[:2]}"
    return limpo + "00"

def extrair_dados_universal(pdf_bytes):
    all_data = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        
        # Identifica Mês/Ano (Ex: 08/2025 ou 03/2025) [cite: 9, 61]
        data_match = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(data_match.group(1)) if data_match else 1
        
        # Identifica o Declarante (CNPJ ou CPF) [cite: 5, 58]
        cnpj_declarante = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", texto_completo)
        nome_declarante = re.search(r"(?:INSTITUTO|JURIPREV|FUNPREVCAP).*?\n", texto_completo, re.I)

        # Captura Beneficiários (Nome, CPF e Proventos) [cite: 8, 22, 68, 70, 80]
        # Busca o CPF como âncora e o valor 'Proventos' ou 'Total de Proventos' próximo
        blocos = re.split(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})", texto_completo)
        
        for i in range(1, len(blocos), 2):
            cpf = re.sub(r'\D', '', blocos[i]) # Regra 3 
            contexto = blocos[i+1]
            
            # Pega o nome que geralmente está antes do CPF
            linhas_antes = blocos[i-1].split('\n')
            nome = linhas_anteriores[-1].strip() if (linhas_anteriores := [l for l in linhas_antes if l.strip()]) else "NOME"

            # Busca o valor na coluna 'Proventos' ou 'Total de Proventos' [cite: 17, 33, 79]
            valor_match = re.search(r"(?:PROVENTOS|TOTAL DE PROVENTOS).*?R\$\s*([\d\.,]+)", contexto, re.I)
            if not valor_match: # Tenta busca apenas pelo valor monetário na linha de totais
                valor_match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", contexto)

            if valor_match:
                all_data.append({
                    'nome': nome[:60].upper(), # Regra 3.2 [cite: 303]
                    'cpf': cpf,
                    'mes': mes_ref,
                    'valor': formatar_valor_tecnico(valor_match.group(1))
                })
    return all_data, cnpj_declarante.group(0) if cnpj_declarante else "", nome_declarante.group(0).strip() if nome_declarante else ""

def gerar_arquivo_dirf(df, d_resp, d_decl):
    linhas = []
    # 1. Registro Dirf (Obrigatório, Ordem 1) [cite: 290, 293]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 2. Registro RESPO (Obrigatório, Ordem 2) [cite: 297, 300]
    linhas.append(f"RESPO|{re.sub(r'\D', '', d_resp['cpf'])}|{d_resp['nome'].upper()}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3. Registro DECPJ (Obrigatório, Ordem 3) [cite: 314, 317]
    linhas.append(f"DECPJ|{re.sub(r'\D', '', d_decl['cnpj'])}|{d_decl['nome'].upper()}|1|{re.sub(r'\D', '', d_resp['cpf'])}|N|N|N|N|N|N|N|N||")
    
    # 4. Registro IDREC [cite: 325]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        # 5. Registro BPFDEC [cite: 330]
        linhas.append(f"BPFDEC|{cpf}|{group['nome'].iloc[0]}||N|N|")
        
        # 6. Registro RTRT (Valores Mensais) [cite: 427, 437]
        meses = [""] * 13 # Jan a Dez + 13º 
        for _, row in group.iterrows():
            meses[int(row['mes'])-1] = row['valor']
        
        # Regra 6: Delimitador Pipe ao final 
        linhas.append(f"RTRT|{'|'.join(meses)}|")

    # 7. Registro FIMDirf (Obrigatório, Último) [cite: 146, 657, 660]
    linhas.append("FIMDirf|")
    return "\n".join(linhas)

# Interface Streamlit
st.title("🚀 Gerador Universal PGD-C")
st.sidebar.header("Dados do Responsável (RESPO)")
r_nome = st.sidebar.text_input("Nome Responsável")
r_cpf = st.sidebar.text_input("CPF Responsável")
r_ddd = st.sidebar.text_input("DDD (ex: 86)")
r_tel = st.sidebar.text_input("Telefone")

uploaded_file = st.file_uploader("Arraste o PDF de qualquer entidade", type="pdf")

if uploaded_file and r_nome:
    dados, cnpj_doc, nome_doc = extrair_dados_universal(uploaded_file.read())
    if dados:
        df = pd.DataFrame(dados)
        st.subheader("✅ Conferência de Dados Extraídos")
        st.table(df) # Exibe para conferência antes de gerar o TXT
        
        d_decl = {"cnpj": cnpj_doc or "00000000000000", "nome": nome_doc or "DECLARANTE NAO ENCONTRADO"}
        d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
        
        txt_final = gerar_arquivo_dirf(df, d_resp, d_decl)
        st.download_button("📥 Baixar Arquivo para PGD-C", txt_final.encode('latin-1'), "DIRF_UNIVERSAL.txt")