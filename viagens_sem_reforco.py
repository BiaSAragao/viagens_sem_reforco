import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(page_title="Monitor Unificado: Base vs e-CITOP", page_icon="🚌", layout="wide")

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

st.markdown("""
    <style>
    .pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; display: inline-block; width: 250px; }
    .pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; display: inline-block; width: 250px; }
    .auto-check { border-left: 4px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 5px 0; border-radius: 5px; color: #2E7D32; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Monitor Unificado de Viagens (Lógica de Linhas Compartilhadas)")

# ==================================================
# BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
files_base = st.sidebar.file_uploader("Suba as Planilhas Base (pode ser mais de uma)", type=["csv", "xlsx"], accept_multiple_files=True)
file_ecitop = st.sidebar.file_uploader("Relatório e-CITOP (Mapa de Controle)", type=["csv", "xlsx"])

if st.sidebar.button("🗑️ Limpar Memória"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÕES DE PROCESSAMENTO
# ==================================================

def carregar_ecitop(file):
    if file is None: return None
    try:
        try:
            df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="utf-8", engine="python")
        
        # B(1) Operadora, E(4) Linha, G(6) Terminal, H(7) Viagem, AA(26) Saída
        df = df.iloc[:, [1, 4, 6, 7, 26]]
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida_real"]
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors='coerce')
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip('0')
        df["operadora"] = df["operadora"].astype(str).str.upper()
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro no e-CITOP: {e}")
        return None

def processar_bases_unificadas(uploaded_files):
    if not uploaded_files: return None
    dfs = []
    for f in uploaded_files:
        try:
            if f.name.lower().endswith(".xlsx"): temp_df = pd.read_excel(f)
            else:
                try: temp_df = pd.read_csv(f, sep=";", encoding="cp1252", engine="python")
                except: temp_df = pd.read_csv(f, sep=";", encoding="utf-8", engine="python")
            dfs.append(temp_df)
        except: continue
    
    if not dfs: return None
    df = pd.concat(dfs, ignore_index=True)
    
    # Colunas: 0 Empresa, 1 Linha, 3 Sentido, 6 Atividade, 14 Programado
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]
    
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip('0')
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], errors="coerce")
    df = df[df["sentido"] != "ocioso"]

    # --- LÓGICA DE HERANÇA DE EMPRESA ---
    # Criamos um mapa de qual empresa opera qual linha baseado nas viagens que têm nome
    mapa_empresas = df[df["empresa"].notna() & (df["empresa"] != "")].groupby("linha_limpa")["empresa"].first().to_dict()

    nao_realizadas = df[df["atividade"] == "não realizada"].copy()
    reforcos = df[df["atividade"] == "reforço"].copy()

    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha_limpa", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha_limpa"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_prog")
        grupo_ref["usado"] = False
        for _, nr in grupo_nr.sort_values("inicio_prog").iterrows():
            cands = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))]
            if cands.empty:
                # Se a empresa está vazia, tenta recuperar do mapa (exceto para a linha 2 que é mista)
                if (pd.isna(nr["empresa"]) or nr["empresa"] == "") and linha != "2":
                    nr["empresa"] = mapa_empresas.get(linha, "DESCONHECIDA")
                falhas.append(nr)
            else:
                grupo_ref.loc[cands.index[0], "usado"] = True
    return pd.DataFrame(falhas)

# ==================================================
# INTERFACE
# ==================================================
df_base_total = processar_bases_unificadas(files_base)
df_citop_total = carregar_ecitop(file_ecitop)

tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

def exibir(df_falhas, df_ecitop, termo_operadora, filtro_linha_2=False):
    if df_falhas is None or df_falhas.empty:
        st.info("Nenhuma falha encontrada.")
        return

    # Filtro de exibição
    if filtro_linha_2:
        df_exibir = df_falhas[df_falhas["linha_limpa"] == "2"]
    else:
        df_exibir = df_falhas[(df_falhas["linha_limpa"] != "2") & (df_falhas["empresa"].astype(str).str.contains(termo_operadora, na=False))]

    if df_exibir.empty:
        st.success("✅ Tudo em ordem para esta categoria.")
        return

    linhas_ord = sorted(df_exibir["linha_limpa"].unique(), key=lambda x: int(x) if x.isdigit() else x)

    for linha in linhas_ord:
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df_exibir[df_exibir["linha_limpa"] == linha].sort_values("inicio_prog")
        
        for _, row in df_l.iterrows():
            h_prog = row["inicio_prog"]
            num_term = "1" if "ida" in row["sentido"] else "2"
            
            st.markdown(f"**🕒 {h_prog.strftime('%H:%M')}**")
            cor = "pc1-box" if num_term == "1" else "pc2-box"
            st.markdown(f'<div class="{cor}">PC{num_term} ({row["sentido"].capitalize()})</div>', unsafe_allow_html=True)

            # Cruzamento no e-CITOP
            if df_ecitop is not None:
                match = df_ecitop[(df_ecitop["linha_limpa"] == linha) & (df_ecitop["num_terminal"].astype(str) == num_term)]
                match_time = match[abs(match["saida_real"] - h_prog) <= timedelta(minutes=15)]
                
                if not match_time.empty:
                    res = match_time.iloc[0]
                    st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP | {res["operadora"]} | Saída: {res["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                else:
                    id_v = f"v_{linha}_{h_prog.strftime('%H%M')}_{num_term}"
                    if id_v in st.session_state.validacoes:
                        st.success("Validado Manualmente")
                    else:
                        st.button("Confirmar Manual no e-CITOP", key=id_v, on_click=lambda i=id_v: st.session_state.validacoes.update({i:True}))
        st.markdown("---")

with tab1: exibir(df_base_total, df_citop_total, "SAO JOAO")
with tab2: exibir(df_base_total, df_citop_total, "ROSA")
with tab3: exibir(df_base_total, df_citop_total, "", filtro_linha_2=True)
