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
# PROCESSAMENTO DO e-CITOP (FIX: ENCODING)
# ==================================================
def carregar_ecitop(file):
    if not file: return None
    try:
        # Tenta ler com Latin-1 (comum em arquivos do Windows/e-CITOP)
        try:
            df = pd.read_csv(file, sep=";", encoding="latin-1", engine="python")
        except:
            df = pd.read_csv(file, sep=";", encoding="iso-8859-1", engine="python")
        
        # Colunas baseadas no arquivo enviado
        colunas = {
            'Nome Operadora': 'operadora',
            'Código Externo Linha': 'linha',
            'Num Terminal': 'terminal',
            'Viagem': 'viagem_tipo',
            'Data Hora Saída Terminal': 'saida_real'
        }
        
        # Filtra apenas se as colunas existirem
        df = df[list(colunas.keys())]
        df.columns = list(colunas.values())

        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        
        # Filtra Ociosas e terminais válidos
        df = df[
            (df["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & 
            (df["terminal"].isin(["1", "2"]))
        ]

        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro ao processar e-CITOP: {e}")
        return None

# ==================================================
# PROCESSAMENTO DA BASE (FIX: ATTR ERROR)
# ==================================================
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
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]

    # --- CORREÇÃO DO ATTRIBUTE ERROR ---
    # Forçamos a coluna empresa a ser string antes de qualquer operação
    df["empresa"] = df["empresa"].astype(str).fillna("DESCONHECIDA")
    df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors="coerce")
    
    df = df.dropna(subset=["inicio_prog"])

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

    return pd.DataFrame(falhas)

# ==================================================
# EXIBIÇÃO
# ==================================================
def exibir(df_base, df_ecitop, operadora_label, linha2=False):
    if df_base is None or df_base.empty:
        st.info("Aguardando arquivos...")
        return

    df = df_base.copy()
    
    # Filtro por operadora garantindo que operadora_label e empresa sejam strings
    if linha2:
        df = df[df["linha_limpa"] == "2"]
    else:
        # Aqui o .str.contains funcionará porque forçamos a conversão acima
        df = df[df["empresa"].str.contains(operadora_label, na=False, case=False)]

    if df.empty:
        st.success("✅ Tudo em ordem")
        return

    linhas_ord = custom_sort_lines(df["linha_limpa"].unique())

    for linha in linhas_ord:
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
                # Busca no e-CITOP
                match = df_ecitop[
                    (df_ecitop["linha_limpa"] == linha) & 
                    (df_ecitop["terminal"] == terminal_busca)
                ]
                
                if not match.empty:
                    # Calcula diferença de tempo
                    match = match.assign(delta=abs(match["saida_real"] - h_prog))
                    match_time = match[match["delta"] <= timedelta(minutes=20)]
                    
                    if not match_time.empty:
                        m = match_time.sort_values("delta").iloc[0]
                        st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP | {m["operadora"]} | Saída: {m["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                        confirmado = True

            if not confirmado:
                key = f"manual_{r['uid']}"
                if key in st.session_state.validacoes:
                    st.success("Validado Manualmente")
                else:
                    st.button("Confirmar Manual", key=key, on_click=lambda k=key: st.session_state.validacoes.update({k: True}))
        st.markdown("---")

# ==================================================
# CARREGAMENTO E ABAS
# ==================================================
df_base = processar_bases(files_base)
df_ecitop = carregar_ecitop(file_ecitop)

tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔄 LINHA 2 (MISTA)"])

with tab1: exibir(df_base, df_ecitop, "JOAO")
with tab2: exibir(df_base, df_ecitop, "ROSA")
with tab3: exibir(df_base, df_ecitop, "", linha2=True)
