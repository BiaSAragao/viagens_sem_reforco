import streamlit as st
import pandas as pd
from datetime import timedelta
import uuid
import io

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
# FUNÇÕES DE PROCESSAMENTO
# ==================================================

def carregar_ecitop(file):
    if not file: return None
    try:
        # Tenta ler com Latin-1 e remove espaços extras nos nomes das colunas
        df = pd.read_csv(file, sep=";", encoding="latin-1", engine="python")
        df.columns = [str(c).strip() for c in df.columns] # Remove espaços invisíveis dos títulos

        # Mapeamento com nomes flexíveis (caso mude algo sutil)
        mapeamento = {
            'Nome Operadora': 'operadora',
            'Código Externo Linha': 'linha',
            'Num Terminal': 'terminal',
            'Viagem': 'viagem_tipo',
            'Data Hora Saída Terminal': 'saida_real'
        }
        
        # Verifica se todas as colunas existem antes de filtrar
        colunas_presentes = [c for c in mapeamento.keys() if c in df.columns]
        if len(colunas_presentes) < 5:
            st.error(f"Colunas encontradas: {list(df.columns)}")
            st.error(f"Faltam colunas no arquivo! Certifique-se que é o relatório MCO original.")
            return None
            
        df = df[colunas_presentes].copy()
        df.columns = [mapeamento[c] for c in colunas_presentes]
        
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        
        # Filtra apenas viagens comerciais (Nor.) e terminais 1 e 2
        df = df[(df["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & (df["terminal"].isin(["1", "2"]))]
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro ao processar e-CITOP: {e}")
        return None

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
    
    df["empresa"] = df["empresa"].astype(str)
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
        indices_ref_usados = set()

        for _, nr in grupo_nr.sort_values("inicio_prog").iterrows():
            candidatos = grupo_ref[
                (~grupo_ref.index.isin(indices_ref_usados)) & 
                (abs(grupo_ref["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))
            ]
            if candidatos.empty:
                item = nr.to_dict()
                item["uid"] = str(uuid.uuid4())
                lista_final.append(item)
            else:
                indices_ref_usados.add(candidatos.index[0])
                
    return pd.DataFrame(lista_final)

# ==================================================
# INTERFACE
# ==================================================
st.title("🚌 Monitor de Viagens (Fluxo em 2 Etapas)")

aba_base, aba_comparacao = st.tabs(["1️⃣ Analisar Base (Reforços)", "2️⃣ Comparar com e-CITOP (GPS)"])

if "df_falhas_limpas" not in st.session_state:
    st.session_state.df_falhas_limpas = None

with aba_base:
    st.header("Passo 1: Identificar Falhas Reais")
    files_base = st.file_uploader("Upload Planilhas Base", type=["csv", "xlsx"], accept_multiple_files=True, key="u1")
    
    if files_base:
        if st.button("Limpar Base (Abater Reforços)"):
            resultado = processar_base_inicial(files_base)
            if resultado is not None and not resultado.empty:
                st.session_state.df_falhas_limpas = resultado
                st.success(f"Encontradas {len(resultado)} falhas reais.")
                st.dataframe(resultado.drop(columns=['uid']))
            else:
                st.success("✅ Nenhuma falha encontrada!")

with aba_comparacao:
    st.header("Passo 2: Confrontar com e-CITOP")
    
    if st.session_state.df_falhas_limpas is None:
        st.warning("⚠️ Primeiro processe a Base na Aba 1.")
    else:
        file_ecitop = st.file_uploader("Upload Relatório e-CITOP (MCO)", type=["csv"], key="u2")
        
        if file_ecitop:
            df_citop = carregar_ecitop(file_ecitop)
            if df_citop is not None:
                op_filtro = st.radio("Escolha a Operadora:", ["SÃO JOÃO", "ROSA", "LINHA 2 (MISTA)"], horizontal=True)
                
                df_view = st.session_state.df_falhas_limpas.copy()
                if op_filtro == "SÃO JOÃO":
                    df_view = df_view[(df_view["empresa"].str.contains("JOAO", case=False)) & (df_view["linha_limpa"] != "2")]
                elif op_filtro == "ROSA":
                    df_view = df_view[(df_view["empresa"].str.contains("ROSA", case=False)) & (df_view["linha_limpa"] != "2")]
                else:
                    df_view = df_view[df_view["linha_limpa"] == "2"]

                if df_view.empty:
                    st.success("Tudo certo para este grupo!")
                else:
                    for linha in sorted(df_view["linha_limpa"].unique(), key=lambda x: int(x) if x.isdigit() else 999):
                        with st.expander(f"🚍 Linha {linha}", expanded=True):
                            grupo_l = df_view[df_view["linha_limpa"] == linha].sort_values("inicio_prog")
                            for _, r in grupo_l.iterrows():
                                h_prog = r["inicio_prog"]
                                terminal = "1" if r["sentido"] == "ida" else "2"
                                
                                c1, c2, c3 = st.columns([1, 1, 3])
                                c1.write(f"**🕒 {h_prog.strftime('%H:%M')}**")
                                c2.markdown(f'<div class="{"pc1-box" if terminal=="1" else "pc2-box"}">PC{terminal}</div>', unsafe_allow_html=True)
                                
                                # Match GPS
                                match = df_citop[(df_citop["linha_limpa"] == linha) & (df_citop["terminal"] == terminal)]
                                match = match.assign(diff=abs(match["saida_real"] - h_prog))
                                match_ok = match[match["diff"] <= timedelta(minutes=20)]
                                
                                if not match_ok.empty:
                                    m = match_ok.sort_values("diff").iloc[0]
                                    c3.markdown(f'<div class="auto-check">✅ GPS: {m["saida_real"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
                                else:
                                    c3.button("Validar Manual", key=r["uid"])
