import streamlit as st
import pdfplumber
import re
import io
import pandas as pd

# Configurações de Leiaute conforme Anexo Único [cite: 204, 210]
ID_ESTRUTURA = "R6GP3ZA" 
ANO_REF = "2025"
ANO_CAL = "2024"

def extrair_valor_pgdc(texto_valor):
    """
    Trata R$ 1.384,00 para 138400 seguindo a Regra 4:
    Sem pontos ou vírgulas, mantendo 2 casas decimais. 
    """
    if not texto_valor: return "0"
    # Remove tudo que não for número ou vírgula
    limpo = re.sub(r'[^\d,]', '', texto_valor)
    
    if ',' in limpo:
        partes = limpo.split(',')
        inteiro = partes[0]
        decimal = partes[1].ljust(2, '0')[:2]
        return f"{inteiro}{decimal}"
    else:
        return limpo + "00"

def extrair_dados_pdf(pdf_bytes):
    dados_mes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Busca Mês/Ano (ex: 03/2025) 
        match_data = re.search(r"(\d{2})/(\d{4})", texto_completo)
        mes_ref = int(match_data.group(1)) if match_data else 3
        
        # Nova lógica: divide o texto por blocos de CPF para não misturar dados
        blocos = re.split(r'(\d{3}\.\d{3}\.\d{3}-\d{2})', texto_completo)
        
        # O primeiro elemento é lixo, os próximos vêm em pares (CPF, Resto do Texto)
        for i in range(1, len(blocos), 2):
            cpf_com_mascara = blocos[i]
            conteudo_bloco = blocos[i+1]
            
            # Busca o nome que geralmente vem antes do CPF no PDF
            # (Pegamos a última linha de texto antes do CPF no bloco anterior ou início deste)
            linhas_anteriores = blocos[i-1].split('\n')
            nome = linhas_anteriores[-1].strip() if linhas_anteriores else "NOME NAO ENCONTRADO"
            
            # Busca o TOTAL DE PROVENTOS dentro do bloco deste servidor
            match_valor = re.search(r"TOTAL DE PROVENTOS\s+R\$\s+([\d\.,]+)", conteudo_bloco)
            
            if match_valor:
                valor_final = extrair_valor_pgdc(match_valor.group(1))
                dados_mes.append({
                    'nome': nome[:60], # Regra 3.2: Tamanho 60 [cite: 218]
                    'cpf': re.sub(r'\D', '', cpf_com_mascara), # Regra 3 
                    'mes': mes_ref,
                    'rendimento': valor_final
                })
    return dados_mes

def gerar_txt_pgdc(df, d_resp, d_decl):
    linhas = []
    # 3.1 Identificador Dirf 
    linhas.append(f"Dirf|{ANO_REF}|{ANO_CAL}|N||{ID_ESTRUTURA}|")
    
    # 3.2 Responsável (RESPO) [cite: 217, 218]
    cpf_r = re.sub(r'\D', '', d_resp['cpf'])
    linhas.append(f"RESPO|{cpf_r}|{d_resp['nome'].upper()}|{d_resp['ddd']}|{d_resp['tel']}||||")
    
    # 3.4 Declarante PJ (DECPJ) [cite: 235]
    cnpj_d = re.sub(r'\D', '', d_decl['cnpj'])
    linhas.append(f"DECPJ|{cnpj_d}|{d_decl['nome'].upper()}|1|{cpf_r}|N|N|N|N|N|N|N|N||")
    
    # Código de Receita Assalariado [cite: 244]
    linhas.append(f"IDREC|0561|")

    for cpf, group in df.groupby('cpf'):
        nome = group['nome'].iloc[0]
        # 3.6 Beneficiário (BPFDEC) 
        linhas.append(f"BPFDEC|{cpf}|{nome.upper()}||N|N|")
        
        # 3.19 Valores Mensais (RTRT) [cite: 342, 394]
        rend_meses = [""] * 13
        for _, row in group.iterrows():
            idx = int(row['mes']) - 1
            rend_meses[idx] = row['rendimento']
            
        linhas.append(f"RTRT|{'|'.join(rend_meses)}|")

    linhas.append("FIMDirf|") # 3.36 Término [cite: 577]
    return "\n".join(linhas)

# --- INTERFACE STREAMLIT ---
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
    if not r_nome or not r_cpf:
        st.error("Preencha os dados do responsável.")
    elif uploaded_files:
        all_data = []
        for f in uploaded_files:
            try:
                dados_extraidos = extrair_dados_pdf(f.read())
                if dados_extraidos:
                    all_data.extend(dados_extraidos)
                else:
                    st.warning(f"Não foram encontrados dados no arquivo {f.name}.")
            except Exception as e:
                st.error(f"Erro ao processar {f.name}: {e}")
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.subheader("✅ Conferência de Valores Extraídos")
            df_conf = df.copy()
            # Formatação visual para conferência humana
            df_conf['Valor Lido'] = df_conf['rendimento'].apply(lambda x: f"R$ {int(x[:-2])},{x[-2:]}")
            st.table(df_conf[['nome', 'cpf', 'Valor Lido']])
            
            d_decl = {"cnpj": "25316695000146", "nome": "JURIPREV TECNOLOGIAS"}
            d_resp = {"nome": r_nome, "cpf": r_cpf, "ddd": r_ddd, "tel": r_tel}
            
            txt_final = gerar_txt_pgdc(df, d_resp, d_decl)
            st.success("Arquivo gerado com sucesso!")
            st.download_button("📥 Baixar Arquivo .TXT", txt_final.encode('latin-1'), "DIRF_JURIPREV_FINAL.txt")