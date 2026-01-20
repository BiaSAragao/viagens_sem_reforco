import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Viagens sem Reforço + e-CITOP",
    page_icon="🚌",
    layout="wide"
)

# Memória para os botões de confirmação manual
if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS para Boxes e Feedback Visual
st.markdown("""
    <style>
    .pc1-box {
        padding: 8px; border-radius: 5px; background-color: #FFA500;
        color: white; font-weight: bold; display: inline-block;
        margin-bottom: 2px; width: 250px;
    }
    .pc2-box {
        padding: 8px; border-radius: 5px; background-color: #1E90FF;
        color: white; font-weight: bold; display: inline-block;
        margin-bottom: 2px; width: 250px;
    }
    .auto-check {
        border-left: 4px solid #2E7D32;
        background-color: #e8f5e9;
        padding: 8px;
        margin: 5px 0 10px 0;
        border-radius: 0 5px 5px 0;
        color: #2E7D32;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Monitor de Viagens: Base vs e-CITOP")

# ==================================================
# BARRA LATERAL (UPLOADS)
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
file_sj = st.sidebar.file_uploader("Base SÃO JOÃO (relExportacao)", type=["csv", "xlsx"])
file_rosa = st.sidebar.file_uploader("Base ROSA (relExportacao)", type=["csv", "xlsx"])
st.sidebar.divider()
file_ecitop = st.sidebar.file_uploader("Relatório e-CITOP (Mapa de Controle)", type=["csv", "xlsx"])

if st.sidebar.button("🗑️ Limpar Memória"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÕES DE PROCESSAMENTO
# ==================================================

def carregar_ecitop(file):
    if file is None: return None
    try:
        # Tenta ler com encodings diferentes para evitar erro de charmap
        try:
            df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="utf-8", engine="python")
        
        # Colunas e-CITOP: B(1) Operadora, E(4) Linha, G(6) Terminal, H(7) Viagem, AA(26) Saída
        df = df.iloc[:, [1, 4, 6, 7, 26]]
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida_real"]
        
        # Limpeza: Remove ociosos e converte horários
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors='coerce')
        df["linha_limpa"] = df["linha"].astype(str).str.lstrip('0')
        df["operadora"] = df["operadora"].astype(str).str.upper()
        
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro ao ler e-CITOP: {e}")
        return None

def processar_base(uploaded_file, termo_ignorar):
    if uploaded_file is None: return None
    try:
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            try:
                df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
            except:
                df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8", engine="python")

        # Colunas Base: 0 Empresa, 1 Linha, 3 Sentido, 6 Atividade, 14 Horário
        df = df.iloc[:, [0, 1, 3, 6, 14]]
        df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

        df["empresa"] = df["empresa"].astype(str).str.upper()
        df = df[~df["empresa"].str.contains(termo_ignorar, na=False)]
        
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip('0')
        df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
        df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
        df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
        df = df[df["sentido"] != "ocioso"]

        nao_realizadas = df[df["atividade"] == "não realizada"].copy()
        reforcos = df[df["atividade"] == "reforço"].copy()

        falhas = []
        for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha_limpa", "sentido"]):
            grupo_ref = reforcos[(reforcos["linha_limpa"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_programado")
            grupo_ref["usado"] = False
            for _, nr in grupo_nr.sort_values("inicio_programado").iterrows():
                candidatos = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_programado"] - nr["inicio_programado"]) <= timedelta(minutes=15))]
                if candidatos.empty:
                    falhas.append(nr)
                else:
                    grupo_ref.loc[candidatos.index[0], "usado"] = True
        return pd.DataFrame(falhas)
    except Exception as e:
        st.error(f"Erro na Base: {e}")
        return None

# ==================================================
# INTERFACE E CRUZAMENTO
# ==================================================
df_ecitop_geral = carregar_ecitop(file_ecitop)

tab1, tab2 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA"])

def exibir_resultados(df_resultado, df_ecitop, operadora_filtro, prefixo):
    if isinstance(df_resultado, pd.DataFrame):
        if df_resultado.empty:
            st.success("✅ Nenhuma falha sem reforço encontrada.")
        else:
            # Filtra o e-CITOP para a operadora da aba
            df_c = None
            if df_ecitop is not None:
                df_c = df_ecitop[df_ecitop["operadora"].str.contains(operadora_filtro, na=False)]

            for linha in sorted(df_resultado["linha_limpa"].unique()):
                st.markdown(f"### 🚍 Linha {linha}")
                df_filtrado = df_resultado[df_resultado["linha_limpa"] == linha]
                
                for _, row in df_filtrado.iterrows():
                    h_prog = row["inicio_programado"]
                    sentido = row["sentido"]
                    # Mapeamento PC1 (Ida = 1) e PC2 (Volta = 2)
                    num_term_alvo = "1" if "ida" in sentido else "2"
                    
                    st.markdown(f"**🕒 {h_prog.strftime('%H:%M')}**")
                    cor = "pc1-box" if num_term_alvo == "1" else "pc2-box"
                    st.markdown(f'<div class="{cor}">PC{num_term_alvo} ({sentido.capitalize()}) — Não Realizada</div>', unsafe_allow_html=True)
                    
                    # Lógica de Cruzamento Automático
                    confirmado_auto = False
                    if df_c is not None:
                        # Busca no e-CITOP: mesma linha, mesmo terminal, dentro de 15 min
                        match = df_c[
                            (df_c["linha_limpa"] == linha) & 
                            (df_c["num_terminal"].astype(str) == num_term_alvo)
                        ]
                        match_time = match[abs(match["saida_real"] - h_prog) <= timedelta(minutes=15)]
                        
                        if not match_time.empty:
                            confirmado_auto = True
                            h_real = match_time.iloc[0]["saida_real"].strftime("%H:%M:%S")
                            st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP (Saída: {h_real})</div>', unsafe_allow_html=True)

                    # Botão Manual (apenas se não confirmou automático)
                    if not confirmado_auto:
                        id_v = f"{prefixo}_{linha}_{h_prog.strftime('%H%M')}_{num_term_alvo}"
                        if id_v in st.session_state.validacoes:
                            if st.button(f"✅ Validado Manualmente (Desfazer)", key=id_v, type="primary"):
                                del st.session_state.validacoes[id_v]
                                st.rerun()
                        else:
                            if st.button(f"Confirmar no e-CITOP", key=id_v):
                                st.session_state.validacoes[id_v] = True
                                st.rerun()
                st.markdown("---")
    else:
        st.info("Faça o upload da planilha para começar.")

with tab1:
    exibir_resultados(processar_base(file_sj, "ROSA"), df_ecitop_geral, "SAO JOAO", "sj")

with tab2:
    exibir_resultados(processar_base(file_rosa, "SAO JOAO"), df_ecitop_geral, "ROSA", "rosa")
