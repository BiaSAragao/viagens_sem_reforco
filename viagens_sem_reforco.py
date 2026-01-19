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

# Inicializa a memória para os status de validação (e-CITOP)
if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS customizado para garantir alinhamento e cores
st.markdown("""
    <style>
    .reportview-container .main .block-container { align-items: flex-start; }
    .pc1-box {
        padding: 8px;
        border-radius: 5px;
        background-color: #FFA500;
        color: white;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 5px;
        width: 250px;
    }
    .pc2-box {
        padding: 8px;
        border-radius: 5px;
        background-color: #1E90FF;
        color: white;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 5px;
        width: 250px;
    }
    .status-check {
        color: #2E7D32;
        font-weight: bold;
        margin-top: 5px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")

# ==================================================
# BARRA LATERAL - UPLOAD
# ==================================================
st.sidebar.header("📁 Enviar Planilhas")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("Limpar Validações"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÃO DE PROCESSAMENTO (IDÊNTICA AO SEU MODELO)
# ==================================================
def processar_dados(uploaded_file, termo_manter, termo_ignorar):
    if uploaded_file is None:
        return None

    # ---------- Leitura ----------
    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except Exception:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    # ---------- Seleção das colunas (A, B, D, G, O) ----------
    colunas_indices = [0, 1, 3, 6, 14]
    if df.shape[1] <= max(colunas_indices):
        return "erro_colunas"

    df = df.iloc[:, colunas_indices]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # ---------- FILTRAGEM (Lógica de Inclusão/Exclusão) ----------
    df["empresa"] = df["empresa"].astype(str).str.upper()
    # Mantém apenas a empresa da aba atual e ignora a outra
    df = df[df["empresa"].str.contains(termo_manter, na=False)]
    df = df[~df["empresa"].str.contains(termo_ignorar, na=False)]

    if df.empty:
        return "vazio"

    # ---------- Tratamentos de Dados ----------
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    # ---------- PAREAMENTO 1x1 ----------
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

# Lógica para SÃO JOÃO
with tab1:
    resultado_sj = processar_dados(file_sj, "SAO JOAO", "ROSA")
    if isinstance(resultado_sj, pd.DataFrame):
        if resultado_sj.empty:
            st.success("✅ Tudo em ordem para São João! Nenhuma falha encontrada.")
        else:
            for linha in sorted(resultado_sj["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_linha = resultado_sj[resultado_sj["linha"] == linha].copy()
                df_linha["Horário"] = df_linha["inicio_programado"].dt.strftime("%H:%M")
                df_linha["PC"] = df_linha["sentido"].map({"ida": "PC1", "volta": "PC2"})

                for _, row in df_linha.iterrows():
                    h = row["Horário"]
                    pc = row["PC"]
                    btn_id = f"sj_{linha}_{h}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {h}**")
                    classe = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{classe}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if btn_id in st.session_state.validacoes:
                        st.markdown('<div class="status-check">✅ Realizada de acordo com e-CITOP</div>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=btn_id):
                            st.session_state.validacoes[btn_id] = True
                            st.rerun()
                st.markdown("---")
    elif resultado_sj == "vazio":
        st.warning("⚠️ Nenhum dado de SÃO JOÃO encontrado nesta planilha.")

# Lógica para ROSA (IDÊNTICA À SÃO JOÃO)
with tab2:
    resultado_rosa = processar_dados(file_rosa, "ROSA", "SAO JOAO")
    if isinstance(resultado_rosa, pd.DataFrame):
        if resultado_rosa.empty:
            st.success("✅ Tudo em ordem para Rosa! Nenhuma falha encontrada.")
        else:
            for linha in sorted(resultado_rosa["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_linha = resultado_rosa[resultado_rosa["linha"] == linha].copy()
                df_linha["Horário"] = df_linha["inicio_programado"].dt.strftime("%H:%M")
                df_linha["PC"] = df_linha["sentido"].map({"ida": "PC1", "volta": "PC2"})

                for _, row in df_linha.iterrows():
                    h = row["Horário"]
                    pc = row["PC"]
                    btn_id = f"rosa_{linha}_{h}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {h}**")
                    classe = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{classe}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if btn_id in st.session_state.validacoes:
                        st.markdown('<div class="status-check">✅ Realizada de acordo com e-CITOP</div>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=btn_id):
                            st.session_state.validacoes[btn_id] = True
                            st.rerun()
                st.markdown("---")
    elif resultado_rosa == "vazio":
        st.warning("⚠️ Nenhum dado de ROSA encontrado nesta planilha.")
