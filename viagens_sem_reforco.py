import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(page_title="Monitor Unificado: Base vs e-CITOP", page_icon="🚌", layout="wide")

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
# FUNÇÕES DE APOIO
# ==================================================
def custom_sort_lines(linhas):
    nums = []
    alfas = []
    for l in linhas:
        s = str(l).strip()
        if s.isdigit(): nums.append(s)
        else: alfas.append(s)
    return sorted(nums, key=int) + sorted(alfas)

def carregar_ecitop(file):
    if not file: return None
    try:
        # Encoding Latin-1 para ler caracteres como 'Ã' e 'Õ' do e-CITOP
        df = pd.read_csv(file, sep=";", encoding="latin-1", engine="python")
        
        # Mapeamento exato baseado no seu CSV
        colunas = {
            'Nome Operadora': 'operadora',
            'Código Externo Linha': 'linha',
            'Num Terminal': 'terminal',
            'Viagem': 'viagem_tipo',
            'Data Hora Saída Terminal': 'saida_real'
        }
        
        df = df[list(colunas.keys())].copy()
        df.columns = list(colunas.values())

        # Limpeza e Conversão
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        
        # Filtro: Apenas viagens comerciais ('Nor.') e terminais de controle (1 e 2)
        df = df[
            (df["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & 
            (df["terminal"].isin(["1", "2"]))
        ]
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro no e-CITOP: {e}")
        return None

def processar_bases(files):
    if not files: return None
    dfs = []
    for f in files:
        try:
            if f.name.lower().endswith(".xlsx"):
                dfs.append(pd.read_excel(f))
            else:
                dfs.append(pd.read_csv(f, sep=";", encoding="latin-1", engine="python"))
        except: continue
    if not dfs: return None

    df = pd.concat(dfs, ignore_index=True)
    # Colunas: Empresa, Linha, Sentido, Atividade, Início Prog.
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    # Forçar tipo string para evitar AttributeError
    df["empresa"] = df["empresa"].astype(str).fillna("DESCONHECIDA")
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
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
            cands = ref_f[(~ref_f.index.isin(usados)) & (abs(ref_f["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))]
            if cands.empty:
                falha = nr.to_dict()
                falha["uid"] = str(uuid.uuid4())
                falhas.append(falha)
            else: usados.add(cands.index[0])
    return pd.DataFrame(falhas)

# ==================================================
# SIDEBAR - DEFINIÇÃO DAS VARIÁVEIS PRIMEIRO
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
files_base = st.sidebar.file_uploader("Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True)
file_ecitop = st.sidebar.file_uploader("Relatório e-CITOP (CSV)", type=["csv"])

if st.sidebar.button("🗑️ Limpar Validações"):
    st.session_state.validacoes = {}
    st.rerun()

# Chamada das funções após a definição dos uploaders
df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

# ==================================================
# EXIBIÇÃO POR ABAS
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
        df_view = df_view[df_view["empresa"].str.contains(filtro_empresa, na=False, case=False)]

    if df_view.empty:
        st.success("✅ Nenhuma falha encontrada para este grupo.")
        return

    for linha in custom_sort_lines(df_view["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df_view[df_view["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            h_prog = r["inicio_prog"]
            terminal_alvo = "1" if r["sentido"] == "ida" else "2"
            css = "pc1-box" if terminal_alvo == "1" else "pc2-box"

            st.markdown(f"**🕒 {h_prog.strftime('%H:%M')}**")
            st.markdown(f'<div class="{css}">PC{terminal_alvo} ({r["sentido"].capitalize()})</div>', unsafe_allow_html=True)

            confirmado = False
            if df_ecitop is not None:
                # Cruzamento lógico com o e-CITOP
                match = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) & 
                    (df_ecitop["terminal"] == terminal_alvo)
                ]
                
                if not match.empty:
                    match = match.assign(diff=abs(match["saida_real"] - h_prog))
                    match_ok = match[match["diff"] <= timedelta(minutes=20)]
                    
                    if not match_ok.empty:
                        m = match_ok.sort_values("diff").iloc[0]
                        st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP | {m["operadora"]} | Saída: {m["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                        confirmado = True

            if not confirmado:
                key = f"manual_{r['uid']}"
                if key in st.session_state.validacoes:
                    st.success("Validado Manualmente")
                else:
                    st.button("Confirmar Manual", key=key, on_click=lambda k=key: st.session_state.validacoes.update({k: True}))
        st.markdown("---")

with tab1: exibir(df_base, df_ecitop, "JOAO")
with tab2: exibir(df_base, df_ecitop, "ROSA")
with tab3: exibir(df_base, df_ecitop, "", linha2=True)
