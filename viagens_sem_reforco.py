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

# ==================================================
# PROCESSAMENTO DO e-CITOP (AJUSTADO AO SEU ARQUIVO)
# ==================================================
def carregar_ecitop(file):
    if not file: return None
    try:
        # Lendo o CSV com o separador ';' que vi no seu arquivo
        df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        
        # Mapeamento pelas colunas exatas do seu arquivo:
        # 'Nome Operadora', 'Código Externo Linha', 'Num Terminal', 'Viagem', 'Data Hora Saída Terminal'
        colunas_necessarias = {
            'operadora': 'Nome Operadora',
            'linha': 'Código Externo Linha',
            'terminal': 'Num Terminal',
            'viagem_tipo': 'Viagem',
            'saida_real': 'Data Hora Saída Terminal'
        }
        
        df_limpo = df[list(colunas_necessarias.values())].copy()
        df_limpo.columns = list(colunas_necessarias.keys())

        # 1. Limpeza de Linha (001 -> 1)
        df_limpo["linha_limpa"] = df_limpo["linha"].astype(str).str.strip().str.lstrip("0")
        
        # 2. Conversão da Data (Seu formato: 2026-01-12 04:20:23.0)
        df_limpo["saida_real"] = pd.to_datetime(df_limpo["saida_real"], errors="coerce")
        
        # 3. Filtro de Ociosas e Terminal 0 (Como você pediu)
        # No seu arquivo, Viagem 'Nor.' é a comercial e 'Oci.' é a ociosa.
        df_limpo = df_limpo[
            (df_limpo["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & 
            (df_limpo["terminal"].astype(str).isin(["1", "2"]))
        ]

        return df_limpo.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro ao processar e-CITOP: {e}")
        return None

# ==================================================
# PROCESSAMENTO DA BASE
# ==================================================
def processar_bases(files):
    if not files: return None
    dfs = []
    for f in files:
        try:
            if f.name.lower().endswith(".xlsx"): dfs.append(pd.read_excel(f))
            else: dfs.append(pd.read_csv(f, sep=";", encoding="cp1252", engine="python"))
        except: continue
    if not dfs: return None

    df = pd.concat(dfs, ignore_index=True)
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")
    
    # Lógica de Reforço (Abaixa a falha se houver reforço próximo)
    nao = df[df["atividade"] == "não realizada"].copy()
    ref = df[df["atividade"] == "reforço"].copy()
    falhas = []

    for (linha, sentido), grp in nao.groupby(["linha_limpa", "sentido"]):
        ref_f = ref[(ref["linha_limpa"] == linha) & (ref["sentido"] == sentido)].sort_values("inicio_prog")
        usados = set()
        for idx, nr in grp.sort_values("inicio_prog").iterrows():
            candidatos = ref_f[(~ref_f.index.isin(usados)) & (abs(ref_f["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))]
            if candidatos.empty:
                falha = nr.to_dict()
                falha["uid"] = str(uuid.uuid4())
                falhas.append(falha)
            else: usados.add(candidatos.index[0])

    df_f = pd.DataFrame(falhas)
    if not df_f.empty: df_f = df_f.drop_duplicates(subset=["linha_limpa", "sentido", "inicio_prog"])
    return df_f

# ==================================================
# INTERFACE E EXIBIÇÃO
# ==================================================
st.sidebar.header("📁 Upload")
files_base = st.sidebar.file_uploader("Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True)
file_ecitop = st.sidebar.file_uploader("Relatório e-CITOP", type=["csv", "xlsx"])

df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

def exibir(df_base, df_ecitop, operadora_label, linha2=False):
    if df_base is None or df_base.empty:
        st.info("Aguardando arquivos...")
        return

    df = df_base.copy()
    if linha2:
        df = df[df["linha_limpa"] == "2"]
    else:
        # Filtro de empresa ignorando acentos/case
        df = df[df["empresa"].str.contains(operadora_label, na=False, case=False)]

    if df.empty:
        st.success("✅ Tudo em ordem")
        return

    for linha in custom_sort_lines(df["linha_limpa"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df[df["linha_limpa"] == linha].sort_values("inicio_prog")

        for _, r in df_l.iterrows():
            h_prog = r["inicio_prog"]
            terminal_busca = "1" if r["sentido"] == "ida" else "2"
            css = "pc1-box" if terminal_busca == "1" else "pc2-box"

            st.markdown(f"**🕒 {h_prog.strftime('%H:%M')}**")
            st.markdown(f'<div class="{css}">PC{terminal_busca} ({r["sentido"].capitalize()})</div>', unsafe_allow_html=True)

            confirmado = False
            if df_ecitop is not None:
                # Cruzamento com e-CITOP
                gps = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) & 
                    (df_ecitop["terminal"].astype(str) == terminal_busca)
                ]
                
                # Tolerância de 20 minutos
                if not gps.empty:
                    gps = gps.assign(delta=abs(gps["saida_real"] - h_prog))
                    gps_match = gps[gps["delta"] <= timedelta(minutes=20)]
                    
                    if not gps_match.empty:
                        g = gps_match.sort_values("delta").iloc[0]
                        st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP | {g["operadora"]} | Saída: {g["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
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
