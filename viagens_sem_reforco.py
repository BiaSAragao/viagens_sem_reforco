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
.pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; width: 220px; text-align: center; }
.pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; width: 220px; text-align: center; }
.auto-check { border-left: 5px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 6px 0; border-radius: 5px; color: #2E7D32; font-weight: bold; border: 1px solid #2E7D32; }
</style>
""", unsafe_allow_html=True)

# ==================================================
# FUNÇÕES DE PROCESSAMENTO (ETAPA 1: BASE)
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
    
    # Seleção de colunas conforme estrutura padrão
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]
    
    # Normalização
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
            # Procura reforço num intervalo de 15 min
            candidatos = grupo_ref[
                (~grupo_ref.index.isin(indices_ref_usados)) & 
                (abs(grupo_ref["inicio_prog"] - nr["inicio_prog"]) <= timedelta(minutes=15))
            ]
            
            if candidatos.empty:
                # Se não tem reforço, é uma falha real
                item = nr.to_dict()
                item["uid"] = str(uuid.uuid4())
                lista_final.append(item)
            else:
                indices_ref_usados.add(candidatos.index[0])
                
    df_resultado = pd.DataFrame(lista_final)
    if not df_resultado.empty:
        df_resultado = df_resultado.drop_duplicates(subset=["linha_limpa", "sentido", "inicio_prog"])
    return df_resultado

# ==================================================
# FUNÇÕES DE PROCESSAMENTO (ETAPA 2: e-CITOP)
# ==================================================
def carregar_ecitop(file):
    if not file: return None
    try:
        df = pd.read_csv(file, sep=";", encoding="latin-1", engine="python")
        # Mapeamento exato do seu arquivo CSV
        df = df[['Nome Operadora', 'Código Externo Linha', 'Num Terminal', 'Viagem', 'Data Hora Saída Terminal']].copy()
        df.columns = ['operadora', 'linha', 'terminal', 'viagem_tipo', 'saida_real']
        
        df["linha_limpa"] = df["linha"].astype(str).str.strip().str.lstrip("0")
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors="coerce")
        df["terminal"] = df["terminal"].astype(str).str.strip()
        
        # Filtra apenas viagens comerciais normais e terminais 1 e 2
        df = df[(df["viagem_tipo"].astype(str).str.contains("Nor", na=False)) & (df["terminal"].isin(["1", "2"]))]
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro no e-CITOP: {e}")
        return None

# ==================================================
# INTERFACE PRINCIPAL
# ==================================================
st.title("🚌 Monitor de Viagens: Fluxo por Etapas")

aba_base, aba_comparacao = st.tabs(["1️⃣ Analisar Base & Download", "2️⃣ Comparar com e-CITOP"])

# Variável de estado para manter os dados entre as abas
if "df_falhas_limpas" not in st.session_state:
    st.session_state.df_falhas_limpas = None

# --- ABA 1: ANALISAR BASE ---
with aba_base:
    st.header("Análise de Reforços")
    files_base = st.file_uploader("Upload das Planilhas Base (CSV/XLSX)", type=["csv", "xlsx"], accept_multiple_files=True, key="u1")
    
    if files_base:
        if st.button("Processar e Abater Reforços"):
            resultado = processar_base_inicial(files_base)
            if resultado is not None and not resultado.empty:
                st.session_state.df_falhas_limpas = resultado
                st.success(f"Análise concluída! Encontradas {len(resultado)} viagens não realizadas sem reforço correspondente.")
                
                # Gerar Excel para Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    resultado.drop(columns=['uid']).to_excel(writer, index=False, sheet_name='Falhas_Sem_Reforco')
                
                st.download_button(
                    label="📥 Baixar Planilha de Falhas Limpas",
                    data=output.getvalue(),
                    file_name="falhas_sem_reforco.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.dataframe(resultado.drop(columns=['uid']))
            else:
                st.success("✅ Todas as não realizadas foram cobertas por reforços!")

# --- ABA 2: COMPARAR e-CITOP ---
with aba_comparacao:
    st.header("Confronto com GPS (e-CITOP)")
    
    if st.session_state.df_falhas_limpas is None:
        st.warning("⚠️ Por favor, primeiro processe a Base na Aba 1.")
    else:
        file_ecitop = st.file_uploader("Upload do Relatório e-CITOP (CSV)", type=["csv"], key="u2")
        
        if file_ecitop:
            df_citop = carregar_ecitop(file_ecitop)
            
            if df_citop is not None:
                # Filtros de Operadora para visualização
                op_filtro = st.selectbox("Filtrar Operadora para Visualização:", ["SÃO JOÃO", "ROSA", "LINHA 2 (MISTA)"])
                
                # Lógica de exibição similar à anterior, mas usando o df_falhas_limpas
                df_view = st.session_state.df_falhas_limpas.copy()
                
                if op_filtro == "SÃO JOÃO":
                    df_view = df_view[(df_view["empresa"].str.contains("JOAO", case=False)) & (df_view["linha_limpa"] != "2")]
                elif op_filtro == "ROSA":
                    df_view = df_view[(df_view["empresa"].str.contains("ROSA", case=False)) & (df_view["linha_limpa"] != "2")]
                else:
                    df_view = df_view[df_view["linha_limpa"] == "2"]

                if df_view.empty:
                    st.success("Nenhuma falha pendente para este grupo!")
                else:
                    for linha in sorted(df_view["linha_limpa"].unique(), key=lambda x: int(x) if x.isdigit() else 999):
                        st.subheader(f"Linha {linha}")
                        grupo_l = df_view[df_view["linha_limpa"] == linha].sort_values("inicio_prog")
                        
                        for _, r in grupo_l.iterrows():
                            h_prog = r["inicio_prog"]
                            terminal_alvo = "1" if r["sentido"] == "ida" else "2"
                            cor_css = "pc1-box" if terminal_alvo == "1" else "pc2-box"
                            
                            st.write(f"**🕒 {h_prog.strftime('%H:%M')}**")
                            st.markdown(f'<div class="{cor_css}">PC{terminal_alvo} ({r["sentido"].capitalize()})</div>', unsafe_allow_html=True)
                            
                            # Comparação com GPS
                            match = df_citop[(df_citop["linha_limpa"] == linha) & (df_citop["terminal"] == terminal_alvo)]
                            match = match.assign(diff=abs(match["saida_real"] - h_prog))
                            match_ok = match[match["diff"] <= timedelta(minutes=20)]
                            
                            if not match_ok.empty:
                                m = match_ok.sort_values("diff").iloc[0]
                                st.markdown(f'<div class="auto-check">✅ Validado via GPS: {m["saida_real"].strftime("%H:%M:%S")} ({m["operadora"]})</div>', unsafe_allow_html=True)
                            else:
                                st.button("Confirmar Manualmente", key=r["uid"])
                        st.divider()
