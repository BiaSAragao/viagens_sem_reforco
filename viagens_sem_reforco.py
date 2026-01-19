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

# CSS original + ajuste de alinhamento
st.markdown("""
    <style>
    .pc1-box {
        padding: 8px; border-radius: 5px; background-color: #FFA500;
        color: white; font-weight: bold; display: inline-block;
        margin-bottom: 5px; width: 250px;
    }
    .pc2-box {
        padding: 8px; border-radius: 5px; background-color: #1E90FF;
        color: white; font-weight: bold; display: inline-block;
        margin-bottom: 5px; width: 250px;
    }
    .status-check { color: #2E7D32; font-weight: bold; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")

# ==================================================
# BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("Limpar todas as conferências"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÃO DE PROCESSAMENTO (IGUAL AO SEU CÓDIGO)
# ==================================================
def processar_empresa(uploaded_file, termo_manter, termo_ignorar):
    if uploaded_file is None:
        return None

    # Leitura original
    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    # Seleção de colunas A, B, D, G, O
    if df.shape[1] < 15:
        return "erro_colunas"

    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # FILTRO EXATO DO SEU EXEMPLO
    df["empresa"] = df["empresa"].astype(str).str.upper()
    # Para São João: mantém SAO JOAO e tira ROSA. Para Rosa: mantém ROSA e tira SAO JOAO.
    df = df[df["empresa"].str.contains(termo_manter, na=False)]
    df = df[~df["empresa"].str.contains(termo_ignorar, na=False)]

    if df.empty:
        return "vazio"

    # Tratamentos originais
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    # Pareamento 1x1 original
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

with tab1:
    res_sj = processar_empresa(file_sj, "SAO JOAO", "ROSA")
    if isinstance(res_sj, pd.DataFrame):
        if res_sj.empty:
            st.success("✅ Nenhuma falha encontrada para São João.")
        else:
            for linha in sorted(res_sj["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_l = res_sj[res_sj["linha"] == linha]
                for _, row in df_l.iterrows():
                    h = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    id_v = f"sj_{linha}_{h}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {h}**")
                    cor = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{cor}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if id_v in st.session_state.validacoes:
                        st.markdown('<div class="status-check">✅ Realizada de acordo com e-CITOP</div>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=id_v):
                            st.session_state.validacoes[id_v] = True
                            st.rerun()
                st.markdown("---")

with tab2:
    res_rosa = processar_empresa(file_rosa, "ROSA", "SAO JOAO")
    if isinstance(res_rosa, pd.DataFrame):
        if res_rosa.empty:
            st.success("✅ Nenhuma falha encontrada para Rosa.")
        else:
            for linha in sorted(res_rosa["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_l = res_rosa[res_rosa["linha"] == linha]
                for _, row in df_l.iterrows():
                    h = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    id_v = f"rosa_{linha}_{h}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {h}**")
                    cor = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{cor}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if id_v in st.session_state.validacoes:
                        st.markdown('<div class="status-check">✅ Realizada de acordo com e-CITOP</div>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=id_v):
                            st.session_state.validacoes[id_v] = True
                            st.rerun()
                st.markdown("---")
