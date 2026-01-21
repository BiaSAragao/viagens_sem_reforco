import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Monitor Unificado: Base vs e-CITOP",
    page_icon="🚌",
    layout="wide"
)

st.markdown("""
<style>
.pc-box {
    padding: 8px;
    border-radius: 5px;
    background-color: #1E88E5;
    color: white;
    font-weight: bold;
    width: 220px;
}
.auto-check {
    border-left: 5px solid #2E7D32;
    background-color: #e8f5e9;
    padding: 10px;
    margin: 6px 0;
    border-radius: 5px;
    color: #2E7D32;
    font-weight: bold;
    border: 1px solid #2E7D32;
}
.auto-fail {
    border-left: 5px solid #C62828;
    background-color: #ffebee;
    padding: 10px;
    margin: 6px 0;
    border-radius: 5px;
    color: #C62828;
    font-weight: bold;
    border: 1px solid #C62828;
}
</style>
""", unsafe_allow_html=True)

st.title("🚌 Monitor Unificado de Viagens")

# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================
def custom_sort_lines(linhas):
    nums, alfas = [], []
    for l in linhas:
        s = str(l).strip()
        if s.isdigit():
            nums.append(s)
        else:
            alfas.append(s)
    return sorted(nums, key=int) + sorted(alfas)

# ==================================================
# LEITURA DO e-CITOP (TXT / CSV)
# ==================================================
def carregar_ecitop(file):
    if not file:
        return None

    try:
        df = pd.read_csv(
            file,
            sep=";",
            encoding="latin-1",
            engine="python"
        )

        col_map = {
            "Código Externo Linha": "linha",
            "Nome Operadora": "operadora",
            "Tipo Viagem": "tipo_viagem",
            "Data Hora Saída Terminal": "saida_real"
        }

        df = df[list(col_map.keys())].copy()
        df.columns = list(col_map.values())

        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["tipo_viagem"] = df["tipo_viagem"].astype(str)

        # Apenas viagens comerciais
        df = df[df["tipo_viagem"].str.contains("Nor", case=False, na=False)]

        return df.dropna(subset=["saida_real"])

    except Exception as e:
        st.error(f"Erro ao ler e-CITOP: {e}")
        return None

# ==================================================
# PROCESSAMENTO DAS BASES
# ==================================================
def processar_bases(files):
    if not files:
        return None

    dfs = []
    for f in files:
        try:
            if f.name.lower().endswith(".xlsx"):
                dfs.append(pd.read_excel(f))
            else:
                dfs.append(pd.read_csv(f, sep=";", encoding="latin-1", engine="python"))
        except:
            continue

    if not dfs:
        return None

    df = pd.concat(dfs, ignore_index=True)

    # Colunas esperadas
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    df["empresa"] = df["empresa"].astype(str)
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")

    df = df.dropna(subset=["inicio_prog"])

    # Apenas NÃO REALIZADA
    nao = df[df["atividade"] == "não realizada"].copy()
    ref = df[df["atividade"] == "reforço"].copy()

    falhas = []

    for (linha, sentido), grp in nao.groupby(["linha_limpa", "sentido"]):
        ref_f = ref[
            (ref["linha_limpa"] == linha) &
            (ref["sentido"] == sentido)
        ].sort_values("inicio_prog")

        usados = set()

        for _, nr in grp.sort_values("inicio_prog").iterrows():
            cands = ref_f[
                (~ref_f.index.isin(usados)) &
                (abs(ref_f["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))
            ]

            if cands.empty:
                falha = nr.to_dict()
                falha["uid"] = str(uuid.uuid4())
                falhas.append(falha)
            else:
                usados.add(cands.index[0])

    return pd.DataFrame(falhas)

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
files_base = st.sidebar.file_uploader(
    "Planilhas Base",
    type=["csv", "xlsx"],
    accept_multiple_files=True
)
file_ecitop = st.sidebar.file_uploader(
    "Relatório e-CITOP (CSV ou TXT)",
    type=["csv", "txt"]
)

df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

# ==================================================
# EXIBIÇÃO
# ==================================================
def exibir(df_base, df_ecitop, filtro_empresa="", linha2=False):

    if df_base is None or df_base.empty:
        st.info("Aguardando upload das planilhas base...")
        return

    df_view = df_base.copy()

    if linha2:
        df_view = df_view[df_view["linha_limpa"] == "2"]
    elif filtro_empresa:
        df_view = df_view[df_view["empresa"].str.contains(filtro_empresa, case=False, na=False)]

    if df_view.empty:
        st.success("✅ Nenhuma falha encontrada.")
        return

    for linha in custom_sort_lines(df_view["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df_view[df_view["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            h = r["inicio_prog"]

            st.markdown(f"**🕒 {h.strftime('%H:%M')}**")
            st.markdown(f'<div class="pc-box">{r["sentido"].capitalize()}</div>', unsafe_allow_html=True)

            confirmado = False

            if df_ecitop is not None:
                m = df_ecitop[df_ecitop["linha_limpa"] == linha]

                if not m.empty:
                    m = m.assign(diff=abs(m["saida_real"] - h))
                    ok = m[m["diff"] <= timedelta(minutes=30)]

                    if not ok.empty:
                        v = ok.sort_values("diff").iloc[0]
                        st.markdown(
                            f'<div class="auto-check">✅ Confirmado no e-CITOP | '
                            f'{v["operadora"]} | Saída: {v["saida_real"].strftime("%H:%M:%S")}</div>',
                            unsafe_allow_html=True
                        )
                        confirmado = True

            if not confirmado:
                st.markdown(
                    '<div class="auto-fail">❌ Não confirmado no e-CITOP</div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")

# ==================================================
# ABAS
# ==================================================
tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

with tab1:
    exibir(df_base, df_ecitop, "JOAO")

with tab2:
    exibir(df_base, df_ecitop, "ROSA")

with tab3:
    exibir(df_base, df_ecitop, linha2=True)
