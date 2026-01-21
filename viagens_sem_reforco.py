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
    if not file: return None
    try:
        # Tenta ler com os encodings mais comuns
        try:
            df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="utf-8", engine="python")

        # Seleção de colunas fixas: 1, 4, 6, 7, 26
        df = df.iloc[:, [1, 4, 6, 7, 26]]
        df.columns = ["operadora", "linha", "terminal", "viagem", "saida_real"]

        # Limpeza de strings
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        df["operadora"] = df["operadora"].astype(str).str.upper().str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')

        # Filtro: Remove ociosas e aceita apenas terminais 1 e 2 (Ignora o 0)
        df = df[
            (~df["viagem"].astype(str).str.contains("Oci.", na=False)) &
            (df["terminal"].isin(["1", "2"]))
        ]

        # Conversão de data (Lida com o formato .0 no final)
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        
        return df.dropna(subset=["saida_real"])

    except Exception as e:
        st.error(f"Erro e-CITOP: {e}")
        return None

# ==================================================
# BASE
# ==================================================
def processar_bases(files):
    if not files: return None
    dfs = []
    for f in files:
        try:
            if f.name.lower().endswith(".xlsx"):
                dfs.append(pd.read_excel(f))
            else:
                dfs.append(pd.read_csv(f, sep=";", encoding="cp1252", engine="python"))
        except: continue

    if not dfs: return None

    df = pd.concat(dfs, ignore_index=True)
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    # Normalização de strings para evitar erros de busca
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["empresa"] = df["empresa"].astype(str).str.upper().str.strip().str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
    
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["inicio_prog"])

    # Lógica de Reforço
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
# EXIBIÇÃO
# ==================================================
def exibir(df_base, df_ecitop, operadora_alvo, linha2=False):
    if df_base is None or df_base.empty:
        st.info("Aguardando arquivos...")
        return

    df = df_base.copy()
    
    # Normaliza a operadora alvo para busca
    op_busca = operadora_alvo.upper().strip()

    if linha2:
        df = df[df["linha_limpa"] == "2"]
    else:
        df = df[(df["linha_limpa"] != "2") & (df["empresa"].str.contains(op_busca, na=False))]

    if df.empty:
        st.success("✅ Tudo em ordem")
        return

    for linha in custom_sort_lines(df["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df[df["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            sentido = r["sentido"]
            h = r["inicio_prog"]
            terminal = "1" if sentido == "ida" else "2"
            css = "pc1-box" if terminal == "1" else "pc2-box"

            st.markdown(f"**🕒 {h.strftime('%H:%M')}**")
            st.markdown(f'<div class="{css}">PC{terminal} ({sentido.capitalize()})</div>', unsafe_allow_html=True)

            confirmado = False
            if df_ecitop is not None:
                # Busca no e-CITOP
                gps = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) &
                    (df_ecitop["terminal"] == terminal)
                ]
                
                # Se não for Linha 2, filtra pela operadora específica
                if not linha2:
                    gps = gps[gps["operadora"].str.contains(op_busca, na=False)]

                # Calcula a diferença de tempo
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

# ==================================================
# RENDERIZAÇÃO DAS ABAS
# ==================================================
with tab1:
    exibir(df_base, df_ecitop, "SAO JOAO")

with tab2:
    exibir(df_base, df_ecitop, "ROSA")

with tab3:
    exibir(df_base, df_ecitop, "", linha2=True)
