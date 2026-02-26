import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute Oficial [cite: 210]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def extrair_valor_exato(texto_valor):
    """
    Garante que R$ 1.384,00 vire 138400.
    Remove tudo que não é número e garante 2 casas decimais.
    """
    if not texto_valor: return "0"
    
    # Remove símbolos e pontos de milhar, mantendo apenas a vírgula e números
    apenas_numeros = re.sub(r'[^\d,]', '', texto_valor)
    
    if ',' in apenas_numeros:
        partes = apenas_numeros.split(',')
        inteiro = partes[0]
        decimal = partes[1].ljust(2, '0')[:2] # Garante 2 dígitos decimais
        return f"{inteiro}{decimal}"
    else:
        return apenas_numeros + "00"

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Identifica Mês de Referência (ex: 03/2025) 
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 3
        
        # Regex Robusta: Captura o bloco do trabalhador e busca o "TOTAL DE PROVENTOS" mais próximo
        # Padrão: Nome -> CPF -> Pula texto até encontrar TOTAL DE PROVENTOS R$ valor
        pattern = r"([A-Z\s]{10,})\n(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)"
        
        for match in re.finditer(pattern, texto_completo, re.DOTALL):
            nome = match.group(1).strip().split('\n')[-1] # Pega apenas a última linha se houver quebra
            cpf = re.sub(r'\D', '', match.group(2))
            valor_bruto = match.group(3)
            
            valor_final = extrair_valor_exato(valor_bruto)
            
            dados_mes.append({
                'nome': nome[:60], # Regra 3.2: Tamanho 60 [cite: 218]
                'cpf': cpf,
                'mes': mes_ref,
                'rendimento': valor_final
            })
    return dados_mes

def gerar_txt(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf [cite: 210]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 217, 218]
    linhas.append(f"RESPO|{re.sub(r'\D', '', d_resp['cpf'])}|{d_resp['nome']}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 235]
    linhas.append(f"DECPJ|{re.sub(r'\D', '', d_decl['cnpj'])}|{d_decl['nome']}|1|{re.sub(r'\D', '', d_resp['cpf'])}|N|N|N|N|N|N|N|N||")
    
    # Código de Receita Assalariado [cite: 244]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC) [cite: 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        rend_meses = [""] * 13
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        # Regra 6: Delimitador Pipe ao final de cada campo 
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 577]
    return "\n".join(linhas)

# Interface Streamlit
st.set_page_config(page_title="Validador PGD-C IPMSF", layout="wide")
st.title("🏦 Gerador IPMSF: Precisão de Dados")

with st.sidebar:
    st.header("Dados do Responsável")
    r_nome = st.text_input("Nome", "RAIMUNDA NONATA PINHEIRO LOPES")
    r_cpf = st.text_input("CPF", "37286960300")
    r_ddd = st.text_input("DDD", "89")
    r_tel = st.text_input("Telefone", "999999999")

uploaded_files = st.file_uploader("Suba os PDFs da folha", type="pdf", accept_multiple_files=True)

if st.button("GERAR ARQUIVO E CONFERIR VALORES", type="primary"):
    if uploaded_files:
        all_data = []
        for f in uploaded_files:
            all_data.extend(extrair_dados_pdf(f.read()))
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("📋 Conferência de Leitura (Verifique antes de baixar)")
            # Exibe os valores formatados para o usuário conferir
            df_display = df.copy()
            df_display['valor_real'] = df_display['rendimento'].apply(lambda x: f"R$ {int(x[:-2])},{x[-2:]}")
            st.table(df_display[['nome', 'cpf', 'valor_real']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "INSTITUTO DE PREVIDENCIA DO MUNICIPIO DE SAO FRANCISCO DO PIAUI"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt_output = gerar_txt(df, d_resp, d_decl)
            st.download_button("📥 Baixar Arquivo Corrigido", txt_output.encode('latin-1'), "DIRF_IPMSF_PRECISAO.txt")