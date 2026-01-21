import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid
import unicodedata

# ==================================================
# CONFIGURAÇÃO E ESTILO
# ==================================================
st.set_page_config(page_title="Monitor Unificado v2", page_icon="🚌", layout="wide")

st.markdown("""
<style>
.pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; width: 100%; text-align: center; }
.pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; width: 100%; text-align: center; }
.auto-check { border-left: 5px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 2px 0; border-radius: 5px; color: #2E7D32; font-weight: bold; border: 1px solid #2E7D32; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)

# ==================================================
# FUNÇÃO PARA NORMALIZAR TEXTO (REMOVE ACENTOS)
# ==================================================
def normalizar_texto(texto):
    if not isinstance(texto, str): return str(texto)
    # Remove acentos e transforma em maiúsculo para comparação robusta
    nfkd_form = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper().strip()

# ==================================================
# CARREGAMENTO INTELIGENTE DO e-CITOP
# ==================================================
def carregar_ecitop(file):
    if not file: return None
    try:
        # Tenta UTF-8 primeiro (baseado nos caracteres estranhos que você enviou)
        try:
            df = pd.read_csv(file, sep=";", encoding="utf-8", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="latin-1", engine="python")

        # Normaliza todos os nomes de colunas do arquivo para tirar acentos
        df.columns = [normalizar_texto(c) for c in df.columns]

        # Mapeamento usando nomes SEM acento e em MAIÚSCULO
        mapeamento = {
            'NOME OPERADORA': 'operadora',
            'CODIGO EXTERNO LINHA': 'linha',
            'NUM TERMINAL': 'terminal',
            'VIAGEM': 'viagem_tipo',
            'DATA HORA SAIDA TERMINAL': 'saida_real'
        }
        
        # Filtra apenas as colunas que mapeamos
        colunas_alvo = [c for c in mapeamento.keys() if c in df.columns]
        
        if len(colunas_alvo) < 5:
            st.error(f"Colunas identificadas no arquivo: {list(df.columns)}")
            st.error("O sistema não encontrou as 5 colunas obrigatórias. Verifique o cabeçalho.")
            return None
            
        df = df[colunas_alvo].copy()
        df.columns = [mapeamento[c] for c in colunas_alvo]
        
        # Limpeza de dados
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        
        # Filtro de viagens comerciais e terminais 1 e 2
        df = df[(df["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & (df["terminal"].isin(["1", "2"]))]
        return df.dropna(subset=["saida_real"])
    
    except Exception as e:
        st.error(f"Erro ao processar e-CITOP: {e}")
        return None

# ==================================================
# RESTANTE DO CÓDIGO (PROCESSAMENTO BASE E INTERFACE)
# ==================================================

def processar_base_inicial(files):
    if not files: return None
    dfs = []
    for f in files:
        try:
            if f.name.lower().endswith(".xlsx"): df = pd.read_excel(f)
            else: df = pd.read_csv(f, sep=";", encoding="latin-1", engine="python")
            dfs.append(df)
        except: continue
    if not dfs: return None
    df = pd.concat(dfs, ignore_index=True)
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["inicio_prog"])
    
    nao_realizadas = df[df["atividade"] == "não realizada"].copy()
    reforcos = df[df["atividade"] == "reforço"].copy()
    lista_final = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha_limpa", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha_limpa"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_prog")
        usados = set()
        for _, nr in grupo_nr.sort_values("inicio_prog").iterrows():
            cands = grupo_ref[(~grupo_ref.index.isin(usados)) & (abs(grupo_ref["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))]
            if cands.empty:
                item = nr.to_dict()
                item["uid"] = str(uuid.uuid4())
                lista_final.append(item)
            else: usados.add(cands.index[0])
    return pd.DataFrame(lista_final)

st.title("🚌 Monitor de Viagens")
aba_base, aba_comparacao = st.tabs(["1️⃣ Analisar Base", "2️⃣ Comparar e-CITOP"])

if "df_falhas_limpas" not in st.session_state:
    st.session_state.df_falhas_limpas = None

with aba_base:
    files_base = st.file_uploader("Upload Base", type=["csv", "xlsx"], accept_multiple_files=True, key="u1")
    if files_base and st.button("Abater Reforços"):
        resultado = processar_base_inicial(files_base)
        st.session_state.df_falhas_limpas = resultado
        st.success(f"{len(resultado)} falhas reais.")
        st.dataframe(resultado)

with aba_comparacao:
    if st.session_state.df_falhas_limpas is None:
        st.warning("Processe a Aba 1 primeiro.")
    else:
        file_ecitop = st.file_uploader("Upload e-CITOP", type=["csv"], key="u2")
        if file_ecitop:
            df_citop = carregar_ecitop(file_ecitop)
            if df_citop is not None:
                op_filtro = st.radio("Empresa:", ["SÃO JOÃO", "ROSA", "LINHA 2"], horizontal=True)
                df_view = st.session_state.df_falhas_limpas.copy()
                
                # Filtro de visualização
                if "JOAO" in op_filtro: df_view = df_view[df_view["empresa"].str.contains("JOAO", case=False)]
                elif "ROSA" in op_filtro: df_view = df_view[df_view["empresa"].str.contains("ROSA", case=False)]
                else: df_view = df_view[df_view["linha_limpa"] == "2"]

                for linha in sorted(df_view["linha_limpa"].unique(), key=lambda x: int(x) if x.isdigit() else 999):
                    with st.expander(f"🚍 Linha {linha}"):
                        for _, r in df_view[df_view["linha_limpa"] == linha].iterrows():
                            h = r["inicio_prog"]
                            term = "1" if r["sentido"] == "ida" else "2"
                            c1, c2, c3 = st.columns([1,1,3])
                            c1.write(h.strftime("%H:%M"))
                            c2.write(f"PC{term}")
                            
                            match = df_citop[(df_citop["linha_limpa"] == linha) & (df_citop["terminal"] == term)]
                            match = match.assign(diff=abs(match["saida_real"] - h))
                            match_ok = match[match["diff"] <= timedelta(minutes=20)]
                            
                            if not match_ok.empty:
                                m = match_ok.sort_values("diff").iloc[0]
                                c3.markdown(f'<div class="auto-check">✅ GPS: {m["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                            else:
                                c3.button("Manual", key=r["uid"])
