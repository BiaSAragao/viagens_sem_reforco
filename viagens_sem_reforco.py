import streamlit as st
import pandas as pd
from datetime import timedelta
import re

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

st.title("🚌 Monitor Unificado de Viagens")

# ==================================================
# BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Upload de Arquivos")
files_base = st.sidebar.file_uploader("Suba as Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True)
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
        
        # Colunas e-CITOP: Operadora(1), Linha(4), Terminal(6), Viagem(7), Saída(26)
        df = df.iloc[:, [1, 4, 6, 7, 26]]
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida_real"]
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors='coerce')
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip('0')
        df["num_terminal"] = df["num_terminal"].astype(str).str.strip()
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
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]
    
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip('0')
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")
    
    # Mapa de empresas para preencher vazios (ex: linha 1 é sempre São João)
    mapa_empresas = df[df["empresa"].notna() & (df["empresa"] != "")].groupby("linha_limpa")["empresa"].first().to_dict()

    nao_realizadas = df[df["atividade"] == "não realizada"].copy()
    reforcos = df[df["atividade"] == "reforço"].copy()

    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha_limpa", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha_limpa"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_prog")
        grupo_ref["usado"] = False
        
        for idx, nr in grupo_nr.sort_values("inicio_prog").iterrows():
            cands = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))]
            if cands.empty:
                if (pd.isna(nr["empresa"]) or nr["empresa"] == "") and linha != "2":
                    nr["empresa"] = mapa_empresas.get(linha, "DESCONHECIDA")
                
                nr_dict = nr.to_dict()
                nr_dict['id_original'] = idx
                falhas.append(nr_dict)
            else:
                grupo_ref.loc[cands.index[0], "usado"] = True
    
    df_result = pd.DataFrame(falhas)
    if not df_result.empty:
        # Remove duplicatas de Linha, Sentido e Horário
        df_result = df_result.drop_duplicates(subset=["linha_limpa", "sentido", "inicio_prog"])
    return df_result

# ==================================================
# INTERFACE
# ==================================================
df_base_total = processar_bases_unificadas(files_base)
df_citop_total = carregar_ecitop(file_ecitop)

tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

def exibir(df_falhas, df_ecitop, termo_operadora, prefixo_aba, filtro_linha_2=False):
    if df_falhas is None or df_falhas.empty:
        st.info("Aguardando upload...")
        return

    # Garante que as colunas de comparação existam e sejam strings
    df_temp = df_falhas.copy()
    df_temp["empresa_str"] = df_temp["empresa"].astype(str).str.upper()
    df_temp["linha_str"] = df_temp["linha_limpa"].astype(str)

    if filtro_linha_2:
        df_exibir = df_temp[df_temp["linha_str"] == "2"]
    else:
        # CORREÇÃO: Usamos a coluna auxiliar empresa_str para evitar o AttributeError
        df_exibir = df_temp[(df_temp["linha_str"] != "2") & (df_temp["empresa_str"].str.contains(termo_operadora, na=False))]

    if df_exibir.empty:
        st.success("✅ Tudo em ordem.")
        return

    for linha in sorted(df_exibir["linha_str"].unique()):
        st.markdown(f"### 🚍 Linha {linha}")
        df_l = df_exibir[df_exibir["linha_str"] == linha].sort_values("inicio_prog")
        
        for _, row in df_l.iterrows():
            h_prog = row["inicio_prog"]
            if pd.isna(h_prog): continue
            
            num_term = "1" if "ida" in str(row["sentido"]).lower() else "2"
            st.markdown(f"**🕒 {h_prog.strftime('%H:%M')}**")
            
            cor = "pc1-box" if num_term == "1" else "pc2-box"
            st.markdown(f'<div class="{cor}">PC{num_term} ({str(row["sentido"]).capitalize()})</div>', unsafe_allow_html=True)

            confirmado_auto = False
            if df_ecitop is not None:
                # Cruzamento com tolerância de 20 min
                match = df_ecitop[(df_ecitop["linha_limpa"] == linha) & (df_ecitop["num_terminal"] == num_term)]
                match_time = match[abs(match["saida_real"] - h_prog) <= timedelta(minutes=20)]
                
                if not match_time.empty:
                    res = match_time.iloc[0]
                    st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP | {res["operadora"]} | Saída: {res["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                    confirmado_auto = True

            if not confirmado_auto:
                id_v = f"btn_{prefixo_aba}_{row['id_original']}_{linha}_{h_prog.strftime('%H%M')}"
                if id_v in st.session_state.validacoes:
                    st.success("Validado Manualmente")
                else:
                    st.button("Confirmar Manual no e-CITOP", key=id_v, on_click=lambda i=id_v: st.session_state.validacoes.update({i:True}))
        st.markdown("---")

with tab1: exibir(df_base_total, df_citop_total, "SAO JOAO", "sj")
with tab2: exibir(df_base_total, df_citop_total, "ROSA", "rosa")
with tab3: exibir(df_base_total, df_citop_total, "", "l2", filtro_linha_2=True)
