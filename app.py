import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute Oficial conforme Anexo Único 
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def extrair_valor_pgdc(texto_valor):
    """
    Converte 'R$ 1.384,00' em '138400' conforme Regra 4.
    Remove pontos de milhar e mantém os centavos.
    """
    if not texto_valor: return "0"
    # Remove R$, espaços e pontos de milhar
    limpo = texto_valor.replace('R$', '').replace('.', '').replace(' ', '').strip()
    # Remove a vírgula para unir os números
    if ',' in limpo:
        limpo = limpo.replace(',', '')
    else:
        # Se não houver vírgula, assume que faltam os centavos
        limpo = limpo + "00"
    return limpo

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        
        # Busca Mês/Ano (ex: 03/2025) [cite: 586]
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 3
        
        # Estratégia de Captura: Busca o CPF e olha as linhas ao redor para Nome e Valor
        # O CPF é a âncora mais confiável [cite: 585, 599]
        cpfs = re.findall(r"(\d{3}\.\d{3}\.\d{3}-\d{2})", texto_completo)
        
        for cpf in cpfs:
            # Localiza o bloco de texto deste servidor específico
            # Busca o "TOTAL DE PROVENTOS" que aparece após o CPF [cite: 594, 609]
            pattern = re.escape(cpf) + r".*?TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)"
            match_valor = re.search(pattern, texto_completo, re.DOTALL)
            
            if match_valor:
                # Busca o nome: geralmente está na linha imediatamente anterior ao CPF
                pattern_nome = r"([A-Z\s]{10,})\n" + re.escape(cpf)
                match_nome = re.search(pattern_nome, texto_completo)
                nome = match_nome.group(1).strip() if match_nome else "NOME NAO IDENTIFICADO"
                
                dados_mes.append({
                    'nome': nome[:60].upper(), # Tamanho máximo 60 [cite: 218, 250]
                    'cpf': re.sub(r'\D', '', cpf), # Apenas números 
                    'mes': mes_ref,
                    'rendimento': extrair_valor_pgdc(match_valor.group(1))
                })
    return dados_mes

def gerar_txt(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf 
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 217, 218]
    cpf_r = re.sub(r'\D', '', d_resp['cpf'])
    linhas.append(f"RESPO|{cpf_r}|{d_resp['nome'].upper()}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 235]
    cnpj_d = re.sub(r'\D', '', d_decl['cnpj'])
    linhas.append(f"DECPJ|{cnpj_d}|{d_decl['nome'].upper()}|1|{cpf_r}|N|N|N|N|N|N|N|N||")
    
    # Identificador de Receita [cite: 240, 244]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário Pessoa Física [cite: 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        rend_meses = [""] * 13 
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        # Garante o caractere delimitador pipe "|" ao final 
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 577]
    return "\n".join(linhas)

# Interface Streamlit
st.set_page_config(page_title="JURIPREV - PGD-C", layout="wide")
st.title("⚖️ Gerador PGD-C: JURIPREV TECNOLOGIAS")

with st.sidebar:
    st.header("👤 Dados do Responsável")
    r_nome = st.text_input("Nome Completo", "")
    r_cpf = st.text_input("CPF (Somente números)", "")
    r_ddd = st.text_input("DDD", "")
    r_tel = st.text_input("Telefone", "")

uploaded_files = st.file_uploader("Suba os PDFs da JURIPREV", type="pdf", accept_multiple_files=True)

if st.button("🚀 GERAR ARQUIVO FINAL", type="primary"):
    if not r_nome or not r_cpf:
        st.error("Preencha os dados do responsável no menu à esquerda.")
    elif uploaded_files:
        all_data = []
        for f in uploaded_files:
            try:
                res = extrair_dados_pdf(f.read())
                if res: all_data.extend(res)
            except Exception as e:
                st.error(f"Erro no arquivo {f.name}: {e}")
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("✅ Conferência de Valores")
            # Mostra o valor legível para você conferir (R$ 1.384,00)
            df_view = df.copy()
            df_view['Valor'] = df_view['rendimento'].apply(lambda x: f"R$ {int(x[:-2])},{x[-2:]}")
            st.table(df_view[['nome', 'cpf', 'Valor']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "JURIPREV TECNOLOGIAS"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt = gerar_txt(df, d_resp, d_decl)
            st.download_button("📥 Baixar Arquivo .TXT", txt.encode('latin-1'), "DIRF_JURIPREV.txt")
        else:
            st.error("Não foi possível encontrar dados de proventos no PDF.")