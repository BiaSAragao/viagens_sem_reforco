import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid

# ==================================================
# CONFIGURAÇÃO
# ==================================================
st.set_page_config(page_title="Monitor Unificado: Base vs e-CITOP", page_icon="🚌", layout="wide")

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

st.markdown("""
<style>
.pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; width: 220px; }
.pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; width: 220px; }
.auto-check { border-left: 5px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 6px 0;
              border-radius: 5px; color: #2E7D32; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🚌 Monitor Unificado de Viagens")

# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================
def custom_sort_lines(linhas):
    nums = []
    alfas = []
    for l in linhas:
        s = str(l).strip()
        if s.isdigit():
            nums.append(s)
        else:
            alfas.append(s)
    return sorted(nums, key=int) + sorted(alfas)

# ==================================================
# e-CITOP
# ==================================================
def carregar_ecitop(file):
    if not file:
        return None

    try:
        try:
            df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="utf-8", engine="python")

        df = df.iloc[:, [1, 4, 6, 7, 26]]
        df.columns = ["operadora", "linha", "terminal", "viagem", "saida_real"]

        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["terminal"] = df["terminal"].astype(str).str.strip()

        df = df[
            (~df["viagem"].astype(str).str.contains("Oci.", na=False)) &
            (df["terminal"].isin(["1", "2"]))
        ]

        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["operadora"] = df["operadora"].astype(str).str.upper()

        return df.dropna(subset=["saida_real"])

    except Exception as e:
        st.error(f"Erro e-CITOP: {e}")
        return None

# ==================================================
# BASE
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
                dfs.append(pd.read_csv(f, sep=";", encoding="cp1252", engine="python"))
        except:
            continue

    if not dfs:
        return None

    df = pd.concat(dfs, ignore_index=True)
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["empresa"] = df["empresa"].astype(str).str.upper().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")

    df = df.dropna(subset=["inicio_prog"])

    nao = df[df["atividade"] == "não realizada"].copy()
    ref = df[df["atividade"] == "reforço"].copy()

    falhas = []

    for (linha, sentido), grp in nao.groupby(["linha_limpa", "sentido"]):
        ref_f = ref[(ref["linha_limpa"] == linha) & (ref["sentido"] == sentido)].sort_values("inicio_prog")
        usados = set()

        for idx, nr in grp.sort_values("inicio_prog").iterrows():
            candidatos = ref_f[
                (~ref_f.index.isin(usados)) &
                (abs(ref_f["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))
            ]

            if candidatos.empty:
                falha = nr.to_dict()
                falha["uid"] = str(uuid.uuid4())
                falhas.append(falha)
            else:
                usados.add(candidatos.index[0])

    df_f = pd.DataFrame(falhas)

    if not df_f.empty:
        df_f = df_f.drop_duplicates(subset=["linha_limpa", "sentido", "inicio_prog"])

    return df_f

# ==================================================
# INTERFACE
# ==================================================
st.sidebar.header("📁 Upload")
files_base = st.sidebar.file_uploader("Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True)
file_ecitop = st.sidebar.file_uploader("Relatório e-CITOP", type=["csv", "xlsx"])

if st.sidebar.button("🗑️ Limpar validações"):
    st.session_state.validacoes = {}
    st.rerun()

df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

# ==================================================
# EXIBIÇÃO
# ==================================================
def exibir(df_base, df_ecitop, operadora, linha2=False):
    if df_base is None or df_base.empty:
        st.info("Aguardando arquivos…")
        return

    df = df_base.copy()

    if linha2:
        df = df[df["linha_limpa"] == "2"]
    else:
        df = df[(df["linha_limpa"] != "2") & (df["empresa"].str.contains(operadora))]

    if df.empty:
        st.success("✅ Tudo em ordem")
        return

    for linha in custom_sort_lines(df["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df[df["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            sentido = r["sentido"]
            h = r["inicio_prog"]

            if sentido == "ida":
                terminal = "1"
                css = "pc1-box"
            elif sentido == "volta":
                terminal = "2"
                css = "pc2-box"
            else:
                continue

            st.markdown(f"**🕒 {h.strftime('%H:%M')}**")
            st.markdown(f'<div class="{css}">PC{terminal} ({sentido.capitalize()})</div>', unsafe_allow_html=True)

            confirmado = False
            if df_ecitop is not None:
                gps = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) &
                    (df_ecitop["terminal"] == terminal) &
                    (df_ecitop["operadora"].str.contains(operadora))
                ]

                gps = gps.assign(delta=abs(gps["saida_real"] - h))
                gps = gps[gps["delta"] <= timedelta(minutes=20)]

                if not gps.empty:
                    g = gps.sort_values("delta").iloc[0]
                    st.markdown(
                        f'<div class="auto-check">✅ Confirmado no e-CITOP | '
                        f'{g["operadora"]} | Saída Real: {g["saida_real"].strftime("%H:%M:%S")}</div>',
                        unsafe_allow_html=True
                    )
                    confirmado = True

            if not confirmado:
                key = f"manual_{r['uid']}"
                if key in st.session_state.validacoes:
                    st.success("Validado Manualmente")
                else:
                    st.button("Confirmar Manual", key=key,
                              on_click=lambda k=key: st.session_state.validacoes.update({k: True}))
        st.markdown("---")

with tab1:
    exibir(df_base, df_ecitop, "SAO JOAO")

with tab2:
    exibir(df_base, df_ecitop, "ROSA")

with tab3:
    exibir(df_base, df_ecitop, "", linha2=True)
