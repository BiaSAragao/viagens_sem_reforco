import streamlit as st
import pandas as pd
from datetime import timedelta
import unicodedata

# Configuração da Página
st.set_page_config(page_title="Check Operacional", layout="wide")

# Função para limpar texto (remove acentos e espaços)
def normalizar(texto):
    if not isinstance(texto, str): return str(texto)
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()

st.title("🚌 Diagnóstico de Viagens")

uploaded_file = st.file_uploader("Envie a planilha aqui para teste", type=["xlsx", "csv"])

if uploaded_file:
    # 1. Leitura Flexível
    if uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='cp1252')

    # 2. Mostrar as colunas encontradas para conferência
    st.write("### 🔍 O que o sistema está vendo:")
    col1, col2, col3 = st.columns(3)
    
    # Pegamos as colunas A(0), B(1), D(3), G(6) e O(14)
    try:
        df_proc = df.iloc[:, [0, 1, 3, 6, 14]].copy()
        df_proc.columns = ["empresa", "linha", "sentido", "atividade", "horario"]
        
        with col1:
            st.write("**Empresas lidas:**", df_proc["empresa"].unique())
        with col2:
            st.write("**Atividades lidas:**", df_proc["atividade"].unique())
        with col3:
            st.write("**Sentidos lidos:**", df_proc["sentido"].unique())

        # 3. Lógica de Filtragem Corrigida (Mais aberta)
        # Normalizamos tudo para evitar erro de acento ou letra grande/pequena
        df_proc["emp_norm"] = df_proc["empresa"].apply(normalizar)
        df_proc["atv_norm"] = df_proc["atividade"].apply(normalizar)
        
        # Filtro São João (Procura qualquer nome que tenha "sao joao")
        sj_dados = df_proc[df_proc["emp_norm"].str.contains("sao joao", na=False)]
        # Filtro Rosa (Procura qualquer nome que tenha "rosa")
        rosa_dados = df_proc[df_proc["emp_norm"].str.contains("rosa", na=False)]

        st.divider()
        
        tab1, tab2 = st.tabs(["SÃO JOÃO", "ROSA"])
        
        with tab1:
            # Aqui buscamos "nao realizada" (sem acento por causa da normalização)
            falhas_sj = sj_dados[sj_dados["atv_norm"].str.contains("nao realizada", na=False)]
            reforcos_sj = sj_dados[sj_dados["atv_norm"].str.contains("reforco", na=False)]
            
            st.write(f"Viagens 'Não Realizadas' encontradas: **{len(falhas_sj)}**")
            
            if not falhas_sj.empty:
                st.dataframe(falhas_sj[["linha", "sentido", "horario", "atividade"]])
            else:
                st.warning("Nenhuma falha detectada com o termo 'Não Realizada'. Verifique a coluna G.")

        with tab2:
            falhas_rosa = rosa_dados[rosa_dados["atv_norm"].str.contains("nao realizada", na=False)]
            st.write(f"Viagens 'Não Realizadas' encontradas: **{len(falhas_rosa)}**")
            
            if not falhas_rosa.empty:
                st.dataframe(falhas_rosa[["linha", "sentido", "horario", "atividade"]])

    except Exception as e:
        st.error(f"Erro ao processar colunas: {e}. Sua planilha tem pelo menos 15 colunas?")
