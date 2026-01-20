import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(page_title="Monitor de Viagens PC1/PC2", page_icon="🚌", layout="wide")

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

st.markdown("""
    <style>
    .pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; display: inline-block; width: 250px; }
    .pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; display: inline-block; width: 250px; }
    .auto-check { border-left: 4px solid #2E7D32; background-color: #e8f5e9; padding: 10px; margin: 5px 0; border-radius: 0 5px 5px 0; font-weight: bold; color: #2E7D32; }
    </style>
    """, unsafe_allow_html=True)

# ==================================================
# FUNÇÕES DE PROCESSAMENTO (CORRIGIDAS)
# ==================================================

def carregar_ecitop_unico(file):
    if file is None: return None
    try:
        if file.name.lower().endswith('.xlsx'):
            df = pd.read_excel(file)
        else:
            # Tenta UTF-8, se falhar tenta CP1252 (comum em sistemas Windows/Excel)
            try:
                df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file, sep=None, engine='python', encoding='cp1252')
        
        # Seleção das colunas solicitadas: B(1), E(4), G(6), H(7), O(14)
        df = df.iloc[:, [1, 4, 6, 7, 14]]
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida"]
        
        # Filtros e-CITOP
        df["operadora"] = df["operadora"].astype(str).str.upper()
        df = df[df["num_terminal"].astype(str) != "0"]
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        
        # Converte saída e remove data inválida
        df["saida"] = pd.to_datetime(df["saida"], errors='coerce')
        df = df.dropna(subset=["saida"])
        df["linha"] = df["linha"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao ler e-CITOP: {e}")
        return None

def processar_base(file, termo_ignorar):
    if file is None: return None
    try:
        if file.name.lower().endswith('.xlsx'):
            df = pd.read_excel(file)
        else:
            try:
                df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file, sep=None, engine='python', encoding='cp1252')

        df = df.iloc[:, [0, 1, 3, 6, 14]]
        df.columns = ["empresa", "linha", "sentido", "atividade", "inicio"]
        
        df["empresa"] = df["empresa"].astype(str).str.upper()
        df = df[~df["empresa"].str.contains(termo_ignorar, na=False)]
        
        df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
        df["inicio"] = pd.to_datetime(df["inicio"], errors='coerce')
        df = df.dropna(subset=["inicio"])
        
        df["sentido_limpo"] = df["sentido"].astype(str).str.lower().str.strip()
        df = df[df["sentido_limpo"] != "ocioso"]
        
        nao_realizadas = df[df["atividade"] == "não realizada"]
        reforcos = df[df["atividade"] == "reforço"]
        
        falhas = []
        for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido_limpo"]):
            grupo_ref = reforcos[(reforcos["linha"] == linha) & (reforcos["sentido_limpo"] == sentido)].sort_values("inicio")
            grupo_ref["usado"] = False
            for _, nr in grupo_nr.sort_values("inicio").iterrows():
                cands = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio"] - nr["inicio"]) <= timedelta(minutes=15))]
                if cands.empty: falhas.append(nr)
                else: grupo_ref.loc[cands.index[0], "usado"] = True
        return pd.DataFrame(falhas)
    except Exception as e:
        st.error(f"Erro ao ler Base: {e}")
        return None

# ==================================================
# INTERFACE
# ==================================================
st.title("🚌 Monitor: Cruzamento com e-CITOP Único")

with st.sidebar:
    st.header("📂 Arquivos Base")
    file_sj_base = st.file_uploader("Base SÃO JOÃO", type=["xlsx", "csv", "txt"], key="b1")
    file_rs_base = st.file_uploader("Base ROSA", type=["xlsx", "csv", "txt"], key="b2")
    
    st.divider()
    st.header("📂 Relatório e-CITOP")
    file_ecitop = st.file_uploader("Planilha Única e-CITOP", type=["xlsx", "csv", "txt"], key="ce")

df_ecitop_geral = carregar_ecitop_unico(file_ecitop)

tab1, tab2 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA"])

def exibir_resultados(df_falhas, df_ecitop, termo_operadora, prefixo):
    if df_falhas is not None and not df_falhas.empty:
        df_citop_aba = None
        if df_ecitop is not None:
            df_citop_aba = df_ecitop[df_ecitop["operadora"].str.contains(termo_operadora, na=False)]

        for linha in sorted(df_falhas["linha"].unique()):
            st.markdown(f"### 🚍 Linha {linha}")
            df_l = df_falhas[df_falhas["linha"] == linha]
            
            for _, row in df_l.iterrows():
                h_prog = row["inicio"]
                sentido_base = row["sentido_limpo"]
                # 1 = Ida/PC1, 2 = Volta/PC2
                num_term_alvo = "1" if any(x in sentido_base for x in ["ida", "pc1"]) else "2"
                
                id_v = f"{prefixo}_{linha}_{h_prog.strftime('%H%M')}_{num_term_alvo}"
                st.write(f"**🕒 Programado: {h_prog.strftime('%H:%M')}**")
                
                cor = "pc1-box" if num_term_alvo == "1" else "pc2-box"
                label_pc = "PC1 (Ida)" if num_term_alvo == "1" else "PC2 (Volta)"
                st.markdown(f'<div class="{cor}">{label_pc} — Não Realizada</div>', unsafe_allow_html=True)
                
                confirmado_auto = False
                if df_citop_aba is not None:
                    # Compara string com string na linha para evitar erro de tipo
                    match = df_citop_aba[
                        (df_citop_aba["linha"].astype(str) == str(linha)) & 
                        (df_citop_aba["num_terminal"].astype(str) == num_term_alvo)
                    ]
                    match_time = match[abs(match["saida"] - h_prog) <= timedelta(minutes=10)]
                    
                    if not match_time.empty:
                        confirmado_auto = True
                        h_real = match_time.iloc[0]["saida"].strftime("%H:%M:%S")
                        st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP (Saída: {h_real})</div>', unsafe_allow_html=True)

                if not confirmado_auto:
                    if id_v in st.session_state.validacoes:
                        if st.button("✅ Validado Manualmente (Desfazer)", key=id_v, type="primary"):
                            del st.session_state.validacoes[id_v]; st.rerun()
                    else:
                        if st.button("Confirmar no e-CITOP", key=id_v):
                            st.session_state.validacoes[id_v] = True; st.rerun()
            st.markdown("---")
    else:
        st.info("Aguardando upload dos arquivos correspondentes...")

with tab1:
    exibir_resultados(processar_base(file_sj_base, "ROSA"), df_ecitop_geral, "SAO JOAO", "sj")

with tab2:
    exibir_resultados(processar_base(file_rs_base, "SAO JOAO"), df_ecitop_geral, "ROSA", "rs")
