import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute Oficial conforme Anexo Único [cite: 210]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def processar_valor_estrito(texto_valor):
    """
    Tratamento técnico: Converte 'R$ 1.384,00' em '138400'.
    Remove todos os caracteres não numéricos e preserva a integridade posicional.
    """
    if not texto_valor: return "0"
    
    # Extrai apenas os dígitos para evitar confusão com separadores de milhar 
    numeros = re.sub(r'\D', '', texto_valor)
    
    # Garante que o valor retornado seja o número inteiro de centavos
    return numeros if numeros else "0"

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        # Consolida texto preservando quebras de linha para identificação de blocos
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Identifica Mês de Referência (ex: 03/2025) 
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 3
        
        # Lógica de Captura por Proximidade Contextual
        # Padrão: Nome (Linha anterior) -> CPF (Âncora) -> Valor (Após Proventos)
        pattern = r"([A-Z\s]{10,})\s+(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)"
        
        for match in re.finditer(pattern, texto_completo, re.DOTALL):
            nome_extraido = match.group(1).strip().split('\n')[-1] # Pega a última linha do bloco de nome
            cpf_limpo = re.sub(r'\D', '', match.group(2)) # Regra 3: Sem máscaras 
            valor_pgdc = processar_valor_estrito(match.group(3))
            
            dados_mes.append({
                'nome': nome_extraido[:60].upper(), # Regra 3.2: Tamanho 60 [cite: 218]
                'cpf': cpf_limpo,
                'mes': mes_ref,
                'rendimento': valor_pgdc
            })
    return dados_mes

def gerar_txt_final(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf [cite: 210]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 217, 218]
    cpf_r = re.sub(r'\D', '', d_resp['cpf'])
    linhas.append(f"RESPO|{cpf_r}|{d_resp['nome'].upper()}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 235]
    cnpj_d = re.sub(r'\D', '', d_decl['cnpj'])
    linhas.append(f"DECPJ|{cnpj_d}|{d_decl['nome'].upper()}|1|{cpf_r}|N|N|N|N|N|N|N|N||")
    
    # Código de Receita Assalariado [cite: 244]
    linhas.append(f"IDREC|0561|")

    # Consolidação por CPF [cite: 247]
    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC) [cite: 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        rend_meses = [""] * 13 
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        # Regra 6: Delimitador Pipe ao final de cada campo 
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 577]
    return "\n".join(linhas)

# Interface Streamlit
st.set_page_config(page_title="JURIPREV - Precisão PGD-C", layout="wide")
st.title("⚖️ Gerador PGD-C: JURIPREV TECNOLOGIAS")

with st.sidebar:
    st.header("👤 Dados do Responsável")
    r_nome = st.text_input("Nome Completo", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

uploaded_files = st.file_uploader("Suba os PDFs da JURIPREV", type="pdf", accept_multiple_files=True)

if st.button("🚀 GERAR ARQUIVO COM PRECISÃO TOTAL", type="primary"):
    if uploaded_files:
        all_data = []
        for f in uploaded_files:
            all_data.extend(extrair_dados_pdf(f.read()))
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("✅ Verificação de Valores (Conferência Estrita)")
            
            # Formatação para conferência humana
            df_check = df.copy()
            df_check['Valor Final (PGD-C)'] = df_check['rendimento']
            df_check['Valor Real (R$)'] = df_check['rendimento'].apply(
                lambda x: f"R$ {int(x[:-2]) if len(x) > 2 else 0},{x[-2:].zfill(2)}"
            )
            st.table(df_check[['nome', 'cpf', 'Valor Real (R$)', 'Valor Final (PGD-C)']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "JURIPREV TECNOLOGIAS"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt_content = gerar_txt_final(df, d_resp, d_decl)
            st.download_button("📥 Baixar Arquivo TXT Validado", txt_content.encode('latin-1'), "DIRF_PRECISAO.txt")