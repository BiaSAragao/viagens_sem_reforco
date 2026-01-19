import streamlit as st
import pandas as pd
from datetime import timedelta
import unicodedata

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(page_title="Monitor de Viagens", page_icon="🚌", layout="wide")

# Inicializa a memória para os status de validação
if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS Customizado
st.markdown("""
    <style>
    .pc1-box { padding: 10px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; margin-bottom: 5px; width: fit-content; min-width: 280px; }
    .pc2-box { padding: 10px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; margin-bottom: 5px; width: fit-content; min-width: 280px; }
    .status-check { color: #2E7D32; font-weight: bold; font-size: 1.1em; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

def remover_acentos(texto):
    if not isinstance(texto, str): return str(texto)
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').upper().strip()

# ==================================================
# FUNÇÃO DE PROCESSAMENTO DE DADOS
# ==================================================
def processar_planilha(uploaded_file, termo_manter):
    if uploaded_file is None: return None
    
    # Leitura
    try:
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, sep=None, encoding="cp1252", engine="python")
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None

    if df.shape[1] < 15:
        st.error(f"A planilha '{uploaded_file.name}' tem poucas colunas ({df.shape[1]}). Verifique se é o arquivo correto.")
        return None
    
    # Seleção de colunas A, B, D, G, O
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    # Normalização para busca
    df["empresa_limpa"] = df["empresa"].apply(remover_acentos)
    termo_busca = remover_acentos(termo_manter)

    # Diagnóstico na Barra Lateral
    with st.sidebar.expander(f"🔍 Diagnóstico: {termo_manter}"):
        nomes_encontrados = df["empresa_limpa"].unique()
        st.write("Nomes na planilha:", nomes_encontrados)

    # Filtragem
    df_filtrado = df[df["empresa_limpa"].str.contains(termo_busca, na=False)].copy()

    if df_filtrado.empty:
        return "vazio"

    # Tratamentos
    df_filtrado["linha"] = df_filtrado["linha"].astype(str).str.strip()
    df_filtrado["sentido"] = df_filtrado["sentido"].astype(str).str.lower().str.strip()
    df_filtrado["atividade"] = df_filtrado["atividade"].astype(str).str.lower().str.strip()
    df_filtrado["inicio_programado"] = pd.to_datetime(df_filtrado["inicio_programado"], errors="coerce")
    
    # Filtra apenas o necessário
    df_filtrado = df_filtrado[df_filtrado["sentido"] != "ocioso"]
    
    nao_realizadas = df_filtrado[df_filtrado["atividade"].str.contains("nao realizada", na=False)]
    reforcos = df_filtrado[df_filtrado["atividade"].str.contains("reforco", na=False)]

    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_programado").copy()
        grupo_ref["usado"] = False
        
        for _, nr in grupo_nr.sort_values("inicio_programado").iterrows():
            # Janela de 15 minutos
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
# INTERFACE
# ==================================================
st.sidebar.header("📁 Importar Planilhas")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv", "txt"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv", "txt"])

if st.sidebar.button("Limpar Validações"):
    st.session_state.validacoes = {}
    st.rerun()

tab_sj, tab_rosa = st.tabs(["🏢 SÃO JOÃO", "🌹 ROSA"])

with tab_sj:
    if file_sj:
        res = processar_planilha(file_sj, "SAO JOAO")
        if isinstance(res, pd.DataFrame):
            if res.empty: st.success("✅ Nenhuma falha encontrada.")
            else:
                for linha in sorted(res["linha"].unique()):
                    st.markdown(f"## 🚍 Linha {linha}")
                    for _, row in res[res["linha"] == linha].iterrows():
                        horario = row["inicio_programado"].strftime("%H:%M")
                        pc = "PC1" if row["sentido"] in ["ida", "pc1"] else "PC2"
                        btn_id = f"sj_{linha}_{horario}_{pc}"
                        st.markdown(f"**🕒 Horário: {horario}**")
                        classe = "pc1-box" if pc == "PC1" else "pc2-box"
                        st.markdown(f'<div class="{classe}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                        if btn_id in st.session_state.validacoes:
                            st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                        else:
                            if st.button(f"Confirmar e-CITOP", key=btn_id):
                                st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                                st.rerun()
        elif res == "vazio": st.warning("⚠️ Empresa 'SAO JOAO' não encontrada nos dados.")

with tab_rosa:
    if file_rosa:
        res = processar_planilha(file_rosa, "ROSA")
        if isinstance(res, pd.DataFrame):
            if res.empty: st.success("✅ Nenhuma falha encontrada.")
            else:
                for linha in sorted(res["linha"].unique()):
                    st.markdown(f"## 🚍 Linha {linha}")
                    for _, row in res[res["linha"] == linha].iterrows():
                        horario = row["inicio_programado"].strftime("%H:%M")
                        pc = "PC1" if row["sentido"] in ["ida", "pc1"] else "PC2"
                        btn_id = f"rosa_{linha}_{horario}_{pc}"
                        st.markdown(f"**🕒 Horário: {horario}**")
                        classe = "pc1-box" if pc == "PC1" else "pc2-box"
                        st.markdown(f'<div class="{classe}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                        if btn_id in st.session_state.validacoes:
                            st.markdown(f'<p class="status-check">✅ {st.session_state.validacoes[btn_id]}</p>', unsafe_allow_html=True)
                        else:
                            if st.button(f"Confirmar e-CITOP", key=btn_id):
                                st.session_state.validacoes[btn_id] = "Realizada de acordo com e-CITOP"
                                st.rerun()
        elif res == "vazio": st.warning("⚠️ Empresa 'ROSA' não encontrada nos dados.")
