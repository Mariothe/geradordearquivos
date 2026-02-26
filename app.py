import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute conforme Anexo Único [cite: 205, 210]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def limpar_valor_monetario(texto):
    """
    Trata valores como 'R$ 1.384,00' para '138400' conforme Regra 4.
    Remove pontos de milhar e símbolos, mantendo a integridade dos centavos.
    """
    if not texto: return "0"
    
    # Remove R$, espaços e pontos de milhar
    limpo = texto.replace('R$', '').replace('.', '').replace(' ', '').strip()
    
    # Se houver vírgula decimal, remove para unir os números (ex: 1384,00 -> 138400)
    if ',' in limpo:
        limpo = limpo.replace(',', '')
    else:
        # Se o PDF trouxer apenas '1384', adicionamos os centavos '00'
        if limpo.isdigit():
            limpo = limpo + "00"
            
    return limpo

def limpar_apenas_digitos(texto):
    """Remove máscaras de CPF/CNPJ conforme Regra 3."""
    return re.sub(r'\D', '', str(texto))

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = "".join([page.extract_text() for page in pdf.pages])
        
        # Identifica Mês/Ano no PDF (ex: 03/2025) [cite: 586]
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 1
        
        # Padrão para capturar Nome, CPF e Proventos [cite: 585, 594, 599, 609]
        # Ajustado para garantir que o valor total seja capturado corretamente
        pattern = r"([A-Z\s]{10,})\s+(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS.*?R\$\s+([\d\.,]+)"
        matches = re.finditer(pattern, texto_completo, re.DOTALL)
        
        for match in matches:
            dados_mes.append({
                'nome': match.group(1).strip()[:60], # Limite 60 caracteres [cite: 218]
                'cpf': limpar_apenas_digitos(match.group(2)),
                'mes': mes_ref,
                'rendimento': limpar_valor_monetario(match.group(3)),
                'imposto': "0" # Pode ser expandido se houver retenção de IRRF
            })
    return dados_mes

def gerar_txt(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf 
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 212, 217]
    linhas.append(f"RESPO|{limpar_apenas_digitos(d_resp['cpf'])}|{d_resp['nome']}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 229, 235]
    linhas.append(f"DECPJ|{limpar_apenas_digitos(d_decl['cnpj'])}|{d_decl['nome']}|1|{limpar_apenas_digitos(d_resp['cpf'])}|N|N|N|N|N|N|N|N||")
    
    # 3.5 Código de Receita [cite: 240, 244]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC) [cite: 245, 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        rend_meses = [""] * 13 # 12 meses + 13º [cite: 464]
        
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        # 3.19 Valores Mensais (RTRT) [cite: 342, 352, 394]
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    # 3.36 Término [cite: 572, 577]
    linhas.append("FIMDirf|")
    return "\n".join(linhas)

# Interface Streamlit
st.set_page_config(page_title="Gerador PGD-C IPMSF", layout="centered")
st.title("🏦 Gerador de Arquivo PGD-C Corrigido")
st.markdown("Este app corrige a leitura de valores monetários da folha IPMSF.")

with st.expander("Dados do Responsável", expanded=False):
    resp_nome = st.text_input("Nome", "RAIMUNDA NONATA PINHEIRO LOPES")
    resp_cpf = st.text_input("CPF", "37286960300")
    resp_ddd = st.text_input("DDD", "89")
    resp_tel = st.text_input("Telefone", "999999999")

uploaded_files = st.file_uploader("Suba os PDFs da folha", type="pdf", accept_multiple_files=True)

if st.button("Gerar Arquivo .TXT", type="primary"):
    if uploaded_files:
        all_data = []
        for f in uploaded_files:
            all_data.extend(extrair_dados_pdf(f.read()))
        
        if all_data:
            df_final = pd.DataFrame(all_data)
            d_decl = {"cnpj": "25316695000146", "nome": "INSTITUTO DE PREVIDENCIA DO MUNICIPIO DE SAO FRANCISCO DO PIAUI"}
            d_resp = {"nome": resp_nome, "cpf": resp_cpf, "ddd": resp_ddd, "tel": resp_tel}
            
            txt_output = gerar_txt(df_final, d_resp, d_decl)
            st.success(f"Processado: {len(df_final)} registros encontrados.")
            st.download_button("Baixar Arquivo Corrigido", txt_output.encode('latin-1'), "DIRF_CORRIGIDA.txt")
        else:
            st.error("Nenhum dado encontrado no PDF. Verifique o formato.")