import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Monitor Unificado: Base x e-CITOP",
    page_icon="🚌",
    layout="wide"
)

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

st.markdown("""
<style>
.pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; width: 220px; }
.pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; width: 220px; }
.auto-check { border-left: 5px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 6px 0;
              border-radius: 5px; color: #2E7D32; font-weight: bold; border: 1px solid #2E7D32; }
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
# CARREGAR e-CITOP (TXT / CSV) — LAYOUT REAL
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

        # Índices REAIS do layout do e-CITOP
        df = df.iloc[:, [
            1,   # Nome Operadora
            4,   # Código Externo Linha
            26,  # Data Hora Saída Terminal
            39,  # Terminal (PC)
            25   # Tipo Viagem
        ]].copy()

        df.columns = [
            "operadora",
            "linha",
            "saida_real",
            "terminal",
            "tipo_viagem"
        ]

        # Normalizações
        df["linha_limpa"] = (
            df["linha"]
            .astype(str)
            .str.strip()
            .str.lstrip("0")
        )

        df["terminal"] = (
            df["terminal"]
            .astype(str)
            .str.replace(".0", "", regex=False)
            .str.strip()
        )

        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")

        # Filtro correto: viagens comerciais (não ociosas) e PCs válidos
        df = df[
            (~df["tipo_viagem"].astype(str).str.contains("oci", case=False, na=False)) &
            (df["terminal"].isin(["1", "2"]))
        ]

        return df.dropna(subset=["saida_real"])

    except Exception as e:
        st.error(f"Erro no e-CITOP: {e}")
        return None

# ==================================================
# PROCESSAR BASES — SOMENTE NÃO REALIZADAS SEM REFORÇO
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

    # Colunas fixas da base
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    df["linha_limpa"] = (
        df["linha"]
        .astype(str)
        .str.strip()
        .str.lstrip("0")
    )

    df["empresa"] = df["empresa"].astype(str)
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")

    df = df.dropna(subset=["inicio_prog"])

    nao = df[df["atividade"] == "não realizada"]
    reforco = df[df["atividade"] == "reforço"]
    realizadas = df[df["atividade"] != "não realizada"]

    falhas = []

    for (linha, sentido), grp in nao.groupby(["linha_limpa", "sentido"]):
        ref_l = reforco[
            (reforco["linha_limpa"] == linha) &
            (reforco["sentido"] == sentido)
        ].sort_values("inicio_prog")

        usados = set()

        for _, nr in grp.sort_values("inicio_prog").iterrows():
            cands = ref_l[
                (~ref_l.index.isin(usados)) &
                (abs(ref_l["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))
            ]

            if not cands.empty:
                usados.add(cands.index[0])
                continue  # tem reforço → ignora

            # Inferir operadora por viagem realizada da mesma linha
            op = "DESCONHECIDA"
            cand = realizadas[realizadas["linha_limpa"] == linha].copy()
            if not cand.empty:
                cand["diff"] = abs(cand["inicio_prog"] - nr["inicio_prog"])
                op = cand.sort_values("diff").iloc[0]["empresa"]

            falha = nr.to_dict()
            falha["empresa"] = op
            falha["uid"] = str(uuid.uuid4())
            falhas.append(falha)

    return pd.DataFrame(falhas)

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
files_base = st.sidebar.file_uploader(
    "Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True
)
file_ecitop = st.sidebar.file_uploader(
    "Relatório e-CITOP (TXT ou CSV)", type=["txt", "csv"]
)

if st.sidebar.button("🗑️ Limpar Validações"):
    st.session_state.validacoes = {}
    st.rerun()

df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

# ==================================================
# EXIBIÇÃO
# ==================================================
tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

def exibir(df_base, df_ecitop, filtro_empresa, linha2=False):
    if df_base is None or df_base.empty:
        st.info("Aguardando upload das planilhas base...")
        return

    df_view = df_base.copy()
    if linha2:
        df_view = df_view[df_view["linha_limpa"] == "2"]
    else:
        df_view = df_view[df_view["empresa"].str.contains(filtro_empresa, case=False, na=False)]

    if df_view.empty:
        st.success("✅ Nenhuma falha encontrada.")
        return

    for linha in custom_sort_lines(df_view["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df_view[df_view["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            h = r["inicio_prog"]
            terminal = "1" if r["sentido"] == "ida" else "2"
            css = "pc1-box" if terminal == "1" else "pc2-box"

            st.markdown(f"**🕒 {h.strftime('%H:%M')}**")
            st.markdown(
                f'<div class="{css}">PC{terminal} ({r["sentido"].capitalize()})</div>',
                unsafe_allow_html=True
            )
            st.caption(f"🏢 Operadora inferida: {r['empresa']}")

            confirmado = False

            if df_ecitop is not None:
                m = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) &
                    (df_ecitop["terminal"] == terminal)
                ]

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
                key = f"manual_{r['uid']}"
                if key in st.session_state.validacoes:
                    st.success("Validado Manualmente")
                else:
                    st.button(
                        "Confirmar Manual",
                        key=key,
                        on_click=lambda k=key: st.session_state.validacoes.update({k: True})
                    )
        st.markdown("---")

with tab1:
    exibir(df_base, df_ecitop, "JOAO")
with tab2:
    exibir(df_base, df_ecitop, "ROSA")
with tab3:
    exibir(df_base, df_ecitop, "", linha2=True)
