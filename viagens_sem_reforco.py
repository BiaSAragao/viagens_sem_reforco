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

# Inicializa a memória para os status de validação
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
        font-size: 1.1em;
        margin-top: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Viagens Não Realizadas sem Reforço")
st.caption("Visual operacional • PC1 (Laranja) • PC2 (Azul)")

# ==================================================
# UPLOAD NA BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Enviar Planilhas")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("Limpar Validações"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÃO DE PROCESSAMENTO (Lógica idêntica ao seu exemplo)
# ==================================================
def processar_viagens(uploaded_file, manter_termo, ignorar_termo):
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

    # ---------- FILTRAGEM EXATA DO SEU EXEMPLO ----------
    df["empresa"] = df["empresa"].astype(str).str.upper()
    
    # Filtro: Contém o nome da empresa desejada E NÃO contém a outra
    df = df[df["empresa"].str.contains(manter_termo, na=False)]
    df = df[~df["empresa"].str.contains(ignorar_termo, na=False)]

    if df.empty:
        return "vazio"

    # ---------- Tratamentos ----------
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "Não realizada"]
    reforcos = df[df["atividade"] == "Reforço"]

    # ---------- Pareamento 1x1 ----------
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
tab_sj, tab_rosa = st.tabs(["🏢 SÃO JOÃO", "🌹 ROSA"])

with tab_sj:
    if file_sj:
        resultado = processar_viagens(file_sj, "SAO JOAO", "ROSA")
        
        if isinstance(resultado, pd.DataFrame):
            if resultado.empty:
                st.success("✅ Nenhuma falha encontrada para São João.")
            else:
                for linha in sorted(resultado["linha"].unique()):
                    st.markdown(f"## 🚍 Linha {linha}")
                    df_l = resultado[resultado["linha"] == linha]
                    for _, row in df_l.iterrows():
                        h = row["inicio_programado"].strftime("%H:%M")
                        pc = "PC1" if row["sentido"] == "ida" else "PC2"
                        btn_id = f"sj_{linha}_{h}_{pc}"
                        
                        st.markdown(f"**🕒 Horário: {h}**")
                        cor_box = "pc1-box" if pc == "PC1" else "pc2-box"
                        st.markdown(f'<div class="{cor_box}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                        
                        if btn_id in st.session_state.validacoes:
                            st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                        else:
                            if st.button("Confirmar no e-CITOP", key=btn_id):
                                st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                                st.rerun()
                    st.markdown("---")
        elif resultado == "vazio":
            st.warning("⚠️ Nenhum dado encontrado para SAO JOAO neste arquivo.")
    else:
        st.info("⬆️ Envie a planilha da São João na barra lateral.")

with tab_rosa:
    if file_rosa:
        resultado = processar_viagens(file_rosa, "ROSA", "SAO JOAO")
        
        if isinstance(resultado, pd.DataFrame):
            if resultado.empty:
                st.success("✅ Nenhuma falha encontrada para Rosa.")
            else:
                for linha in sorted(resultado["linha"].unique()):
                    st.markdown(f"## 🚍 Linha {linha}")
                    df_l = resultado[resultado["linha"] == linha]
                    for _, row in df_l.iterrows():
                        h = row["inicio_programado"].strftime("%H:%M")
                        pc = "PC1" if row["sentido"] == "ida" else "PC2"
                        btn_id = f"rosa_{linha}_{h}_{pc}"
                        
                        st.markdown(f"**🕒 Horário: {h}**")
                        cor_box = "pc1-box" if pc == "PC1" else "pc2-box"
                        st.markdown(f'<div class="{cor_box}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                        
                        if btn_id in st.session_state.validacoes:
                            st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                        else:
                            if st.button("Confirmar no e-CITOP", key=btn_id):
                                st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                                st.rerun()
                    st.markdown("---")
        elif resultado == "vazio":
            st.warning("⚠️ Nenhum dado encontrado para ROSA neste arquivo.")
    else:
        st.info("⬆️ Envie a planilha da Rosa na barra lateral.")

