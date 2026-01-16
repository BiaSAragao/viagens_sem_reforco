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
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")

# ==================================================
# UPLOAD
# ==================================================
uploaded_file = st.file_uploader(
    "📁 Envie a planilha CSV",
    type=["xlsx", "csv", "txt"]
)

# ==================================================
# PROCESSAMENTO
# ==================================================
if uploaded_file is not None:

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
        st.error("❌ A planilha não possui todas as colunas necessárias.")
        st.stop()

    df = df.iloc[:, colunas_indices]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # ---------- FILTRO: IGNORAR EMPRESA COM 'ROSA' ----------
    df["empresa"] = df["empresa"].astype(str).str.upper()
    df = df[~df["empresa"].str.contains("ROSA", na=False)]

    if df.empty:
        st.warning("⚠️ Nenhum dado restante após filtrar empresas 'ROSA'.")
        st.stop()

    # ---------- Tratamentos de Dados ----------
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    # ==================================================
    # PAREAMENTO 1x1
    # ==================================================
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

    resultado_df = pd.DataFrame(falhas)

    if resultado_df.empty:
        st.success("✅ Tudo em ordem! Nenhuma falha encontrada.")
        st.stop()

    # ==================================================
    # INTERFACE VISUAL ALINHADA À ESQUERDA
    # ==================================================
    linhas_disponiveis = sorted(df["linha"].unique())
    
    st.sidebar.header("Filtros de Exibição")
    linhas_selecionadas = st.sidebar.multiselect(
        "Selecione as linhas",
        options=linhas_disponiveis,
        default=linhas_disponiveis
    )

    for linha in linhas_selecionadas:
        df_linha = resultado_df[resultado_df["linha"] == linha].copy()

        if not df_linha.empty:
            st.markdown(f"## 🚍 Linha {linha}")
            
            df_linha["Horário"] = df_linha["inicio_programado"].dt.strftime("%H:%M")
            df_linha["PC"] = df_linha["sentido"].map({"ida": "PC1", "volta": "PC2"})

            horarios = sorted(df_linha["Horário"].unique())

            for h in horarios:
                # Exibe o horário como um sub-cabeçalho alinhado à esquerda
                st.markdown(f"**🕒 Horário: {h}**")
                
                pcs = df_linha[df_linha["Horário"] == h]["PC"].tolist()
                
                # Exibe cada PC um abaixo do outro, ou lado a lado, mas sempre à esquerda
                if "PC1" in pcs:
                    st.markdown(f'<div class="pc1-box">🔸 PC1 (Ida) — Não Realizada</div>', unsafe_allow_html=True)
                
                if "PC2" in pcs:
                    st.markdown(f'<div class="pc2-box">🔹 PC2 (Volta) — Não Realizada</div>', unsafe_allow_html=True)
                
                # Pequeno espaço entre horários
                st.write("") 

            st.markdown("---")

else:

    st.info("⬆️ Envie a planilha para iniciar a análise operacional.")

