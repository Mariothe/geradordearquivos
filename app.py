import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações conforme o Leiaute Oficial enviado
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

   def limpar_numero(texto):
    """
    Garante a leitura correta de valores como R$ 1.384,00 para 138400.
    Remove pontos de milhar, símbolos e trata a vírgula decimal.
    """
    if not texto: return "0"
    
    # Remove o símbolo R$ e espaços
    texto = texto.replace('R$', '').strip()
    
    # Se o valor tem vírgula (ex: 1.384,00)
    if ',' in texto:
        # Remove o ponto (milhar) e depois a vírgula (decimal)
        texto = texto.replace('.', '').replace(',', '')
    else:
        # Se for um número limpo, apenas remove caracteres não numéricos
        texto = re.sub(r'\D', '', texto)
        # Se o valor vier sem os dois zeros dos centavos, acrescenta-os
        if len(texto) > 0 and len(texto) < 4:
            texto = texto + "00"
            
    return texto
def extrair_dados_ipmsf(pdf_bytes):
    """Extrai Nome, CPF e Valores do PDF do IPMSF"""
    beneficiarios = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto = "".join([page.extract_text() for page in pdf.pages])
        
        # Identifica o mês no topo do PDF (ex: 03/2025)
        match_data = re.search(r"(\d{2})/(\d{4})", texto)
        mes_ref = int(match_data.group(1)) if match_data else 1
        
        # Padrão para capturar os blocos de cada servidor no seu PDF
        pattern = r"([A-Z\s]{10,})\s+(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS.*?R\$\s+([\d\.,]+).*?TOTAL DE DESCONTOS\s+R\$\s+([\d\.,]*)"
        matches = re.finditer(pattern, texto, re.DOTALL)
        
        for match in matches:
            valor_desc = match.group(4) if match.group(4) else "0,00"
            beneficiarios.append({
                'nome': match.group(1).strip()[:60],
                'cpf': limpar_numero(match.group(2)),
                'mes': mes_ref,
                'rendimento': limpar_numero(match.group(3)),
                'imposto': limpar_numero(valor_desc)
            })
    return beneficiarios

def gerar_arquivo_pgdc(df, d_resp, d_decl):
    """Gera o TXT com delimitadores Pipe | e registros obrigatórios"""
    linhas = []
    # 3.1 Identificador Dirf
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    # 3.2 Responsável (RESPO)
    linhas.append(f"RESPO|{limpar_numero(d_resp['cpf'])}|{d_resp['nome']}|{d_resp['ddd']}|{d_resp['tel']}||||")
    # 3.4 Declarante (DECPJ)
    linhas.append(f"DECPJ|{limpar_numero(d_decl['cnpj'])}|{d_decl['nome']}|1|{limpar_numero(d_resp['cpf'])}|N|N|N|N|N|N|N|N||")
    # 3.5 Código de Receita (IDREC)
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC)
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        rend_meses = [""] * 13 # 12 meses + 13º
        imp_meses = [""] * 13
        
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            imp_meses[idx] = row['imposto']
            
        # 3.19 Registros de Valores Mensais (RTRT e RTIRF)
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")
        if any(v != "" for v in imp_meses):
            linhas.append(f"RTIRF|{'|'.join(imp_meses)}|")

    linhas.append("FIMDirf|")
    return "\n".join(linhas)

# --- INTERFACE WEB ---
st.set_page_config(page_title="Gerador PGD-C IPMSF", page_icon="🏦")
st.title("🏦 Conversor de Folha IPMSF para PGD-C")
st.info("Suba os PDFs das folhas mensais e gere o arquivo para importação na Receita Federal.")

with st.expander("Dados do Responsável pelo Preenchimento", expanded=True):
    r_nome = st.text_input("Nome do Responsável", "RAIMUNDA NONATA PINHEIRO LOPES")
    r_cpf = st.text_input("CPF do Responsável", "37286960300")
    r_ddd = st.text_input("DDD", "89")
    r_tel = st.text_input("Telefone", "999999999")

files = st.file_uploader("Arraste seus PDFs aqui", type="pdf", accept_multiple_files=True)

if st.button("🚀 Gerar Arquivo Consolidado", use_container_width=True):
    if files:
        all_data = []
        for f in files:
            all_data.extend(extrair_dados_ipmsf(f.read()))
        
        df_final = pd.DataFrame(all_data)
        d_decl = {"cnpj": "25316695000146", "nome": "INSTITUTO DE PREVIDENCIA DO MUNICIPIO DE SAO FRANCISCO DO PIAUI"}
        d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
        
        txt_output = gerar_arquivo_pgdc(df_final, d_resp, d_decl)
        
        st.success(f"Sucesso! {len(df_final['cpf'].unique())} servidores processados.")
        st.download_button("📥 Baixar Arquivo .TXT para o PGD-C", txt_output.encode('latin-1'), "DIRF_PGDC_S_FRANCISCO.txt")
    else:
        st.error("Por favor, suba ao menos um arquivo PDF.")