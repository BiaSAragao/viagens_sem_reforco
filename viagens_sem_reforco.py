import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Monitor de Viagens - São João & Rosa",
    page_icon="🚌",
    layout="wide"
)

# Inicializa a memória para os status de validação
if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS Customizado
st.markdown("""
    <style>
    .pc1-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #FFA500;
        color: white;
        font-weight: bold;
        margin-bottom: 5px;
        width: fit-content;
        min-width: 280px;
    }
    .pc2-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #1E90FF;
        color: white;
        font-weight: bold;
        margin-bottom: 5px;
        width: fit-content;
        min-width: 280px;
    }
    .status-check {
        color: #2E7D32;
        font-weight: bold;
        font-size: 1.1em;
        margin-top: 5px;
        padding-left: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Monitor Operacional de Viagens")
st.caption("Cores: PC1 (Laranja) | PC2 (Azul) • Validação individual por viagem")

# ==================================================
# FUNÇÃO DE PROCESSAMENTO DE DADOS
# ==================================================
def processar_planilha(uploaded_file, termo_manter, termo_ignorar):
    if uploaded_file is None:
        return None
    
    # Leitura do arquivo
    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    # Seleção de colunas A, B, D, G, O (índices 0, 1, 3, 6, 14)
    if df.shape[1] < 15:
        return "erro_colunas"
    
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # Limpeza e Filtros de Empresa
    df["empresa"] = df["empresa"].astype(str).str.upper()
    
    # Lógica: Manter a empresa correta E ignorar a outra
    mask = (df["empresa"].str.contains(termo_manter, na=False)) & \
           (~df["empresa"].str.contains(termo_ignorar, na=False))
    df = df[mask]

    if df.empty:
        return "vazio"

    # Tratamentos de Dados
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    # Pareamento 1x1
    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_programado").copy()
        grupo_ref["usado"] = False
        
        for _, nr in grupo_nr.sort_values("inicio_programado").iterrows():
            candidatos = grupo_ref[
                (~grupo_ref["usado"]) & 
                (abs(grupo_ref["inicio_programado"] - nr["inicio_programado"]) <= timedelta(minutes=15))
            ]
            if candidatos.empty:
                falhas.append(nr)
            else:
                grupo_ref.loc[candidatos.index[0], "usado"] = True
    
    return pd.DataFrame(falhas)

# ==================================================
# BARRA LATERAL (UPLOADS)
# ==================================================
st.sidebar.header("📁 Importar Planilhas")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("Limpar todas as validações"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# INTERFACE EM ABAS
# ==================================================
tab_sj, tab_rosa = st.tabs(["🏢 SÃO JOÃO", "🌹 ROSA"])

# --- ABA SÃO JOÃO ---
with tab_sj:
    if file_sj:
        res_sj = processar_planilha(file_sj, "SAO JOAO", "ROSA")
        
        if isinstance(res_sj, str):
            st.error("Erro no arquivo ou dados não encontrados.")
        elif res_sj.empty:
            st.success("✅ Nenhuma falha encontrada para São João.")
        else:
            for linha in sorted(res_sj["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_l = res_sj[res_sj["linha"] == linha].sort_values("inicio_programado")
                
                for _, row in df_l.iterrows():
                    horario = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    # ID único para o botão não dar conflito
                    btn_id = f"btn_sj_{linha}_{horario}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {horario}**")
                    classe = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{classe}">{pc} ({row["sentido"].upper()}) — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if btn_id in st.session_state.validacoes:
                        st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=btn_id):
                            st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                            st.rerun()
                st.markdown("---")
    else:
        st.info("⬆️ Por favor, envie a planilha da São João na barra lateral.")

# --- ABA ROSA ---
with tab_rosa:
    if file_rosa:
        res_rosa = processar_planilha(file_rosa, "ROSA", "SAO JOAO")
        
        if isinstance(res_rosa, str):
            st.error("Erro no arquivo ou dados não encontrados.")
        elif res_rosa.empty:
            st.success("✅ Nenhuma falha encontrada para Rosa.")
        else:
            for linha in sorted(res_rosa["linha"].unique()):
                st.markdown(f"## 🚍 Linha {linha}")
                df_l = res_rosa[res_rosa["linha"] == linha].sort_values("inicio_programado")
                
                for _, row in df_l.iterrows():
                    horario = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    btn_id = f"btn_rosa_{linha}_{horario}_{pc}"
                    
                    st.markdown(f"**🕒 Horário: {horario}**")
                    classe = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{classe}">{pc} ({row["sentido"].upper()}) — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if btn_id in st.session_state.validacoes:
                        st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                    else:
                        if st.button("Confirmar no e-CITOP", key=btn_id):
                            st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                            st.rerun()
                st.markdown("---")
    else:
        st.info("⬆️ Por favor, envie a planilha da Rosa na barra lateral.")
