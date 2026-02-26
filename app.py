import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute Oficial conforme Anexo Único [cite: 204, 210]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def extrair_valor_pgdc(texto_valor):
    """
    Converte 'R$ 1.384,00' em '138400'.
    Regra 4: Sem pontos ou vírgulas, mantendo centavos.
    """
    if not texto_valor: return "0"
    
    # Remove R$, espaços e pontos de milhar (o erro estava aqui)
    passo1 = texto_valor.replace('R$', '').replace('.', '').strip()
    
    # Trata a vírgula decimal
    if ',' in passo1:
        partes = passo1.split(',')
        inteiro = partes[0]
        decimal = partes[1].ljust(2, '0')[:2] # Garante 2 dígitos 
        return f"{inteiro}{decimal}"
    else:
        return passo1 + "00"

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Busca Mês/Ano (ex: 03/2025) [cite: 586]
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 1
        
        # Padrão para capturar Nome, CPF e TOTAL DE PROVENTOS [cite: 585, 594]
        pattern = r"([A-Z\s]{10,})\n(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)"
        
        for match in re.finditer(pattern, texto_completo, re.DOTALL):
            nome = match.group(1).strip().split('\n')[-1]
            cpf = re.sub(r'\D', '', match.group(2)) # Regra 3: Sem máscaras 
            valor_final = extrair_valor_pgdc(match.group(3))
            
            dados_mes.append({
                'nome': nome[:60], # Regra 3.2: Tamanho 60 [cite: 218]
                'cpf': cpf,
                'mes': mes_ref,
                'rendimento': valor_final
            })
    return dados_mes

def gerar_txt_pgdc(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf [cite: 210]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) - Campos em branco para preenchimento [cite: 217]
    cpf_r = re.sub(r'\D', '', d_resp['cpf'])
    linhas.append(f"RESPO|{cpf_r}|{d_resp['nome']}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) - JURIPREV TECNOLOGIAS 
    cnpj_d = re.sub(r'\D', '', d_decl['cnpj'])
    linhas.append(f"DECPJ|{cnpj_d}|{d_decl['nome']}|1|{cpf_r}|N|N|N|N|N|N|N|N||")
    
    # Código de Receita Assalariado [cite: 244]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC) [cite: 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        rend_meses = [""] * 13
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|") # Regra 6: Delimitador final 

    linhas.append("FIMDirf|") # 3.36 Término [cite: 577]
    return "\n".join(linhas)

# Interface Web Streamlit
st.set_page_config(page_title="JURIPREV - Gerador PGD-C", layout="wide")
st.title("⚖️ Gerador PGD-C: JURIPREV TECNOLOGIAS")

with st.sidebar:
    st.header("👤 Dados do Responsável")
    r_nome = st.text_input("Nome Completo", "")
    r_cpf = st.text_input("CPF (Somente números)", "")
    r_ddd = st.text_input("DDD", "")
    r_tel = st.text_input("Telefone", "")

uploaded_files = st.file_uploader("Suba os PDFs da folha JURIPREV", type="pdf", accept_multiple_files=True)

if st.button("🚀 GERAR ARQUIVO PARA RECEITA FEDERAL", type="primary"):
    if not r_nome or not r_cpf:
        st.error("Preencha os dados do responsável no menu lateral.")
    elif uploaded_files:
        all_data = []
        for f in uploaded_files:
            all_data.extend(extrair_dados_pdf(f.read()))
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("✅ Conferência de Valores")
            # Mostra R$ 1.384,00 em vez de 138400 para facilitar sua conferência
            df_conf = df.copy()
            df_conf['Valor Lido'] = df_conf['rendimento'].apply(lambda x: f"R$ {int(x[:-2])},{x[-2:]}")
            st.table(df_conf[['nome', 'cpf', 'Valor Lido']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "JURIPREV TECNOLOGIAS"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt_final = gerar_txt_pgdc(df, d_resp, d_decl)
            st.download_button("📥 Baixar Arquivo TXT", txt_final.encode('latin-1'), "DIRF_JURIPREV_2025.txt")
        else:
            st.error("Erro na leitura do PDF. Verifique o arquivo.")