import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute Oficial conforme Anexo Único 
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def formatar_valor_pgdc(texto_valor):
    """
    CORREÇÃO DEFINITIVA: Converte 'R$ 1.384,00' em '138400'.
    Remove qualquer caractere que não seja número e trata os centavos. 
    """
    if not texto_valor: return "0"
    
    # Mantém apenas os dígitos numéricos
    apenas_numeros = re.sub(r'\D', '', texto_valor)
    
    # Se o texto original não tinha centavos explícitos (raro em folha), 
    # a lógica de 'apenas_numeros' já traz o valor cheio.
    return apenas_numeros

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Identifica Mês/Ano no PDF (ex: 03/2025)
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 3
        
        # Lógica de Captura por Proximidade: Nome -> CPF -> Total Proventos
        # O CPF é usado como âncora para isolar cada servidor
        pattern = r"([A-Z\s]{10,})\n(\d{3}\.\d{3}\.\d{3}-\d{2}).*?TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)"
        
        for match in re.finditer(pattern, texto_completo, re.DOTALL):
            nome_limpo = match.group(1).strip().split('\n')[-1]
            cpf_limpo = re.sub(r'\D', '', match.group(2)) # Regra 3 
            valor_bruto = match.group(3)
            
            # Formatação para o PGD-C
            valor_pgdc = formatar_valor_pgdc(valor_bruto)
            
            dados_mes.append({
                'nome': nome_limpo[:60].upper(), # Regra 3.2 
                'cpf': cpf_limpo,
                'mes': mes_ref,
                'rendimento': valor_pgdc
            })
    return dados_mes

def gerar_txt_pgdc(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf [cite: 205, 210]
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 212, 217]
    cpf_r = re.sub(r'\D', '', d_resp['cpf'])
    linhas.append(f"RESPO|{cpf_r}|{d_resp['nome'].upper()}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 229, 235]
    cnpj_d = re.sub(r'\D', '', d_decl['cnpj'])
    linhas.append(f"DECPJ|{cnpj_d}|{d_decl['nome'].upper()}|1|{cpf_r}|N|N|N|N|N|N|N|N||")
    
    linhas.append(f"IDREC|0561|") # Código de Receita Assalariado [cite: 240, 244]

    # Consolidação Anual por CPF
    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário Pessoa Física (BPFDEC) [cite: 245, 250]
        linhas.append(f"BPFDEC|{cpf}|{nome}||N|N|")
        
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        rend_meses = [""] * 13 # Jan a Dez + 13º
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        # Garante o Pipe final em cada registro 
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 572, 577]
    return "\n".join(linhas)

# Interface Streamlit
st.set_page_config(page_title="JURIPREV - Gerador PGD-C", layout="wide")
st.title("⚖️ Gerador PGD-C: JURIPREV TECNOLOGIAS")

with st.sidebar:
    st.header("👤 Dados do Responsável")
    r_nome = st.text_input("Nome Completo", "MARIO FLAVIO PEREIRA")
    r_cpf = st.text_input("CPF (Somente números)", "84598000325")
    r_ddd = st.text_input("DDD", "86")
    r_tel = st.text_input("Telefone", "32116868")

uploaded_files = st.file_uploader("Suba os PDFs da folha JURIPREV", type="pdf", accept_multiple_files=True)

if st.button("🚀 GERAR ARQUIVO PARA RECEITA FEDERAL", type="primary"):
    if uploaded_files:
        all_data = []
        for f in uploaded_files:
            all_data.extend(extrair_dados_pdf(f.read()))
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("✅ Conferência de Valores (Confirme antes de baixar)")
            
            # Mostra o valor legível para o usuário conferir
            df_conf = df.copy()
            df_conf['Valor Lido'] = df_conf['rendimento'].apply(lambda x: f"R$ {int(x[:-2])},{x[-2:]}" if len(x) > 2 else f"R$ 0,{x.zfill(2)}")
            st.table(df_conf[['nome', 'cpf', 'Valor Lido']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "JURIPREV TECNOLOGIAS"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt_final = gerar_txt_pgdc(df, d_resp, d_decl)
            st.success("Arquivo gerado com sucesso!")
            st.download_button("📥 Baixar Arquivo .TXT", txt_final.encode('latin-1'), "DIRF_JURIPREV_FINAL.txt")