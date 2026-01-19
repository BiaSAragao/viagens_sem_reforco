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

# ==================================================
# CSS
# ==================================================
st.markdown("""
<style>
.pc1-box {
    padding: 8px;
    border-radius: 5px;
    background-color: #FFA500;
    color: white;
    font-weight: bold;
    display: inline-block;
    width: 260px;
    margin-bottom: 5px;
}
.pc2-box {
    padding: 8px;
    border-radius: 5px;
    background-color: #1E90FF;
    color: white;
    font-weight: bold;
    display: inline-block;
    width: 260px;
    margin-bottom: 5px;
}
</style>
""", unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")
st.caption("PC1 = Ida | PC2 = Volta • Conferência com e-CITOP")

# ==================================================
# ESTADO
# ==================================================
if "confirmadas" not in st.session_state:
    st.session_state.confirmadas = set()

# ==================================================
# UPLOADS
# ==================================================
st.header("📂 Upload dos Arquivos")

col1, col2 = st.columns(2)

with col1:
    file_sj = st.file_uploader(
        "Empresa São João",
        type=["xlsx", "csv", "txt"],
        key="sj"
    )

with col2:
    file_rosa = st.file_uploader(
        "Empresa Rosa",
        type=["xlsx", "csv", "txt"],
        key="rosa"
    )

# ==================================================
# FUNÇÃO DE PROCESSAMENTO
# ==================================================
def processar_viagens(uploaded_file, empresa_nome):

    if uploaded_file is None:
        st.info("⬆️ Envie a planilha para iniciar.")
        return

    # ---------- Leitura ----------
    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except Exception:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    # ---------- Seleção de colunas ----------
    colunas_indices = [0, 1, 3, 6, 14]

    if df.shape[1] <= max(colunas_indices):
        st.error("❌ Colunas insuficientes.")
        return

    df = df.iloc[:, colunas_indices]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # ---------- Filtro empresa ----------
    df["empresa"] = df["empresa"].astype(str).str.upper()
    df = df[df["empresa"].str.contains(empresa_nome, na=False)]

    if df.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        return

    # ---------- Tratamentos ----------
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    # ---------- Pareamento ----------
    falhas = []

    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido"]):

        grupo_ref = reforcos[
            (reforcos["linha"] == linha) &
            (reforcos["sentido"] == sentido)
        ].sort_values("inicio_programado").copy()

        grupo_ref["usado"] = False
        grupo_nr = grupo_nr.sort_values("inicio_programado")

        for _, nr in grupo_nr.iterrows():
            candidatos = grupo_ref[
                (~grupo_ref["usado"]) &
                (abs(grupo_ref["inicio_programado"] - nr["inicio_programado"])
                 <= timedelta(minutes=15))
            ]

            if candidatos.empty:
                falhas.append(nr)
            else:
                grupo_ref.loc[candidatos.index[0], "usado"] = True

    resultado_df = pd.DataFrame(falhas)

    if resultado_df.empty:
        st.success("✅ Nenhuma falha encontrada.")
        return

    # ---------- INTERFACE ----------
    linhas = sorted(resultado_df["linha"].unique())

    for linha in linhas:
        st.markdown(f"## 🚍 Linha {linha}")

        df_linha = resultado_df[resultado_df["linha"] == linha].copy()
        df_linha["Horário"] = df_linha["inicio_programado"].dt.strftime("%H:%M")
        df_linha["PC"] = df_linha["sentido"].map({"ida": "PC1", "volta": "PC2"})

        for horario in sorted(df_linha["Horário"].unique()):
            st.markdown(f"**🕒 Horário: {horario}**")

            bloco = df_linha[df_linha["Horário"] == horario]

            for _, row in bloco.iterrows():
                pc = row["PC"]
                id_viagem = f"{empresa_nome}_{linha}_{horario}_{pc}"

                if id_viagem in st.session_state.confirmadas:
                    st.success(f"✔ {pc} confirmada via e-CITOP")
                    continue

                col_a, col_b = st.columns([3, 1])

                with col_a:
                    if pc == "PC1":
                        st.markdown(
                            '<div class="pc1-box">🔸 PC1 (Ida) — Não Realizada</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            '<div class="pc2-box">🔹 PC2 (Volta) — Não Realizada</div>',
                            unsafe_allow_html=True
                        )

                with col_b:
                    if st.button(
                        "✔ Realizada (e-CITOP)",
                        key=id_viagem
                    ):
                        st.session_state.confirmadas.add(id_viagem)
                        st.experimental_rerun()

            st.write("")
        st.markdown("---")

# ==================================================
# ABAS
# ==================================================
tab_sj, tab_rosa = st.tabs(["🚌 São João", "🌹 Rosa"])

with tab_sj:
    processar_viagens(file_sj, "SAO JOAO")

with tab_rosa:
    processar_viagens(file_rosa, "ROSA")
