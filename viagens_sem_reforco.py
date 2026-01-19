import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Viagens sem Reforço",
    page_icon="🚌",
    layout="wide"
)

# Memória para os botões de confirmação
if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS para Boxes e Botões Estilizados
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
    /* Estilo para o container da validação */
    .valida-container {
        border-left: 4px solid #2E7D32;
        background-color: #e8f5e9;
        padding: 5px 10px;
        margin: 5px 0 15px 0;
        border-radius: 0 5px 5px 0;
        width: fit-content;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")

# ==================================================
# BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
file_sj = st.sidebar.file_uploader("Planilha para aba SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha para aba ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("🗑️ Limpar Tudo"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÃO DE PROCESSAMENTO
# ==================================================
def processar_dados(uploaded_file, termo_para_ignorar):
    if uploaded_file is None:
        return None

    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    if df.shape[1] < 15:
        return "erro_colunas"

    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    df["empresa"] = df["empresa"].astype(str).str.upper()
    df = df[~df["empresa"].str.contains(termo_para_ignorar, na=False)]

    if df.empty: return "vazio"

    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_programado").copy()
        grupo_ref["usado"] = False
        grupo_nr = grupo_nr.sort_values("inicio_programado")

        for _, nr in grupo_nr.iterrows():
            candidatos = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_programado"] - nr["inicio_programado"]) <= timedelta(minutes=15))]
            if candidatos.empty:
                falhas.append(nr)
            else:
                grupo_ref.loc[candidatos.index[0], "usado"] = True

    return pd.DataFrame(falhas)

# ==================================================
# INTERFACE EM ABAS
# ==================================================
tab1, tab2 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA"])

def exibir_resultados(df_resultado, prefixo):
    if isinstance(df_resultado, pd.DataFrame):
        if df_resultado.empty:
            st.success("✅ Nenhuma falha encontrada.")
        else:
            for linha in sorted(df_resultado["linha"].unique()):
                st.markdown(f"### 🚍 Linha {linha}")
                df_filtrado = df_resultado[df_resultado["linha"] == linha]
                
                for _, row in df_filtrado.iterrows():
                    h = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    id_v = f"{prefixo}_{linha}_{h}_{pc}"
                    
                    # Layout da Viagem
                    st.markdown(f"**🕒 {h}**")
                    cor = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{cor}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    # Lógica do Botão Alternável
                    esta_validado = id_v in st.session_state.validacoes
                    
                    if esta_validado:
                        # Se já clicou, mostra botão verde de "Desfazer"
                        if st.button(f"✅ Realizada (e-CITOP) - Clique p/ desfazer", key=id_v, type="primary"):
                            del st.session_state.validacoes[id_v]
                            st.rerun()
                    else:
                        # Se não clicou, mostra botão padrão
                        if st.button(f"Confirmar no e-CITOP", key=id_v):
                            st.session_state.validacoes[id_v] = True
                            st.rerun()
                st.markdown("---")

with tab1:
    exibir_resultados(processar_dados(file_sj, "ROSA"), "sj")

with tab2:
    exibir_resultados(processar_dados(file_rosa, "SAO JOAO"), "rosa")
