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
# FUNÇÕES DE PROCESSAMENTO
# ==================================================

def processar_ecitop(file, termo_operadora):
    if file is None: return None
    try:
        # Colunas e-CITOP: B(1) Operadora, E(4) Linha, G(6) Num Terminal, H(7) Viagem, O(14) Saída
        df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file, sep=None, engine='python', encoding='cp1252')
        df = df.iloc[:, [1, 4, 6, 7, 14]]
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida"]
        
        # Filtros e-CITOP
        df["operadora"] = df["operadora"].astype(str).str.upper()
        df = df[df["operadora"].str.contains(termo_operadora, na=False)]
        
        # Ignora Ociosas (Num Terminal 0 ou texto Oci.)
        df = df[df["num_terminal"].astype(str) != "0"]
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        
        df["saida"] = pd.to_datetime(df["saida"], errors='coerce')
        df["linha"] = df["linha"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao ler e-CITOP: {e}")
        return None

def processar_base(file, termo_ignorar):
    if file is None: return None
    # Colunas Base: A(0), B(1), D(3), G(6), O(14)
    df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file, sep=None, engine='python', encoding='cp1252')
    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio"]
    
    df["empresa"] = df["empresa"].astype(str).str.upper()
    df = df[~df["empresa"].str.contains(termo_ignorar, na=False)]
    
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio"] = pd.to_datetime(df["inicio"], errors='coerce')
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

# ==================================================
# INTERFACE
# ==================================================
st.title("🚌 Monitor Operacional: Base vs e-CITOP (PC1/PC2)")

with st.sidebar:
    st.header("📂 Arquivos")
    st.subheader("São João")
    sj_base = st.file_uploader("Base SJ", type=["xlsx", "csv"], key="b1")
    sj_citop = st.file_uploader("e-CITOP SJ", type=["xlsx", "csv"], key="c1")
    st.divider()
    st.subheader("Rosa")
    rs_base = st.file_uploader("Base Rosa", type=["xlsx", "csv"], key="b2")
    rs_citop = st.file_uploader("e-CITOP Rosa", type=["xlsx", "csv"], key="c2")

tab1, tab2 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA"])

def exibir(df_falhas, df_citop, prefixo):
    if df_falhas is not None and not df_falhas.empty:
        for linha in sorted(df_falhas["linha"].unique()):
            st.markdown(f"### 🚍 Linha {linha}")
            df_l = df_falhas[df_falhas["linha"] == linha]
            
            for _, row in df_l.iterrows():
                h_prog = row["inicio"]
                sentido_base = row["sentido_limpo"]
                # Mapeia Sentido para Num Terminal
                num_term_alvo = "1" if "ida" in sentido_base or "pc1" in sentido_base else "2"
                
                id_v = f"{prefixo}_{linha}_{h_prog.strftime('%H%M')}_{num_term_alvo}"
                st.write(f"**🕒 Programado: {h_prog.strftime('%H:%M')}**")
                
                cor = "pc1-box" if num_term_alvo == "1" else "pc2-box"
                label_pc = "PC1 (Ida)" if num_term_alvo == "1" else "PC2 (Volta)"
                st.markdown(f'<div class="{cor}">{label_pc} — Não Realizada</div>', unsafe_allow_html=True)
                
                # Validação automática com e-CITOP
                confirmado_auto = False
                if df_citop is not None:
                    # Filtra por linha e num_terminal (sentido)
                    match = df_citop[
                        (df_citop["linha"] == str(linha)) & 
                        (df_citop["num_terminal"].astype(str) == num_term_alvo)
                    ]
                    # Verifica janela de 10 minutos
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
    else: st.info("Aguardando upload dos arquivos correspondentes...")

with tab1: exibir(processar_base(sj_base, "ROSA"), processar_ecitop(sj_citop, "SAO JOAO"), "sj")
with tab2: exibir(processar_base(rs_base, "SAO JOAO"), processar_ecitop(rs_citop, "ROSA"), "rs")
