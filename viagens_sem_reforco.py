import streamlit as st
import pandas as pd
from datetime import timedelta

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(page_title="Monitor e-CITOP", page_icon="🚌", layout="wide")

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# Estilos Visuais
st.markdown("""
    <style>
    .pc1-box { padding: 10px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; margin-bottom: 5px; width: 280px; }
    .pc2-box { padding: 10px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; margin-bottom: 5px; width: 280px; }
    .auto-check { border-left: 5px solid #2E7D32; background-color: #e8f5e9; padding: 12px; margin: 10px 0; border-radius: 5px; font-weight: bold; color: #1B5E20; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# ==================================================
# PROCESSAMENTO DE DADOS
# ==================================================

def carregar_ecitop(file):
    if file is None: return None
    try:
        # Lendo e-CITOP (Mapa de Controle Operacional)
        df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        
        # Colunas Reais do seu arquivo:
        # B(1): Nome Operadora | E(4): Código Externo Linha | G(6): Num Terminal | H(7): Viagem | AA(26): Data Hora Saída Terminal
        df = df.iloc[:, [1, 4, 6, 7, 26]] 
        df.columns = ["operadora", "linha", "num_terminal", "viagem", "saida_real"]
        
        # Limpeza
        df = df[df["num_terminal"].astype(str) != "0"]
        df = df[~df["viagem"].astype(str).str.contains("Oci.", na=False)]
        
        # Ajuste de Horário e Linha
        df["saida_real"] = pd.to_datetime(df["saida_real"], errors='coerce')
        df["linha_limpa"] = df["linha"].astype(str).str.lstrip('0')
        df["operadora"] = df["operadora"].astype(str).str.upper()
        
        return df.dropna(subset=["saida_real"])
    except Exception as e:
        st.error(f"Erro no e-CITOP: {e}")
        return None

def processar_base(file, termo_ignorar):
    if file is None: return None
    try:
        # Lendo Base (Exportação Viagem)
        df = pd.read_csv(file, sep=";", encoding="cp1252", engine="python")
        
        # Colunas Reais: A(0): Empresa | B(1): Linha | D(3): Sentido | G(6): Atividade | O(14): Início Programado
        df = df.iloc[:, [0, 1, 3, 6, 14]]
        df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_prog"]
        
        # Filtros
        df = df[~df["empresa"].astype(str).str.contains(termo_ignorar, na=False)]
        df["inicio_prog"] = pd.to_datetime(df["inicio_prog"], dayfirst=True, errors='coerce')
        df["linha_limpa"] = df["linha"].astype(str).str.lstrip('0')
        df["atividade"] = df["atividade"].astype(str).str.lower()
        
        # Lógica de Reforço
        nr = df[df["atividade"] == "não realizada"].copy()
        ref = df[df["atividade"] == "reforço"].copy()
        
        falhas = []
        for (lin, sen), grupo_nr in nr.groupby(["linha_limpa", "sentido"]):
            grupo_ref = ref[(ref["linha_limpa"] == lin) & (ref["sentido"] == sen)].sort_values("inicio_prog")
            grupo_ref["usado"] = False
            for _, row_nr in grupo_nr.sort_values("inicio_prog").iterrows():
                cands = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_prog"] - row_nr["inicio_prog"]) <= timedelta(minutes=15))]
                if cands.empty: falhas.append(row_nr)
                else: grupo_ref.loc[cands.index[0], "usado"] = True
        return pd.DataFrame(falhas)
    except Exception as e:
        st.error(f"Erro na Base: {e}")
        return None

# ==================================================
# INTERFACE STREAMLIT
# ==================================================
st.title("📊 Monitor de Validação e-CITOP")

with st.sidebar:
    st.header("📂 Carregar Dados")
    f_sj = st.file_uploader("Base SÃO JOÃO", type=["csv"])
    f_rs = st.file_uploader("Base ROSA", type=["csv"])
    st.divider()
    f_citop = st.file_uploader("Relatório e-CITOP (Mapa)", type=["csv"])

df_citop_geral = carregar_ecitop(f_citop)

t1, t2 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA"])

def exibir(df_falhas, df_citop, operadora_alvo, prefixo):
    if df_falhas is not None and not df_falhas.empty:
        # Filtra e-CITOP pela operadora
        df_c = None
        if df_citop is not None:
            df_c = df_citop[df_citop["operadora"].str.contains(operadora_alvo, na=False)]

        for linha in sorted(df_falhas["linha_limpa"].unique()):
            st.markdown(f"### 🚍 Linha {linha}")
            for _, row in df_falhas[df_falhas["linha_limpa"] == linha].iterrows():
                h_prog = row["inicio_prog"]
                sentido = row["sentido"]
                # Mapeia: Ida -> 1, Volta -> 2
                term_alvo = "1" if sentido.lower() == "ida" else "2"
                
                st.write(f"**🕒 Programado: {h_prog.strftime('%H:%M')}**")
                classe = "pc1-box" if term_alvo == "1" else "pc2-box"
                st.markdown(f'<div class="{classe}">{sentido} — Não Realizada</div>', unsafe_allow_html=True)
                
                # AUTO-CHECK
                check_ok = False
                if df_c is not None:
                    match = df_c[(df_c["linha_limpa"] == linha) & (df_c["num_terminal"].astype(str) == term_alvo)]
                    # Compara se há saída em até 10 min
                    match_time = match[abs(match["saida_real"] - h_prog) <= timedelta(minutes=10)]
                    
                    if not match_time.empty:
                        check_ok = True
                        h_real = match_time.iloc[0]["saida_real"].strftime("%H:%M:%S")
                        st.markdown(f'<div class="auto-check">✅ Confirmado no e-CITOP (Saída: {h_real})</div>', unsafe_allow_html=True)

                # Botões Manuais
                id_btn = f"{prefixo}_{linha}_{h_prog.strftime('%H%M')}_{term_alvo}"
                if not check_ok:
                    if id_btn in st.session_state.validacoes:
                        if st.button("✅ Validado Manual (Desfazer)", key=id_btn, type="primary"):
                            del st.session_state.validacoes[id_btn]; st.rerun()
                    else:
                        st.button("Confirmar Manualmente", key=id_btn, on_click=lambda id=id_btn: st.session_state.validacoes.update({id:True}))
            st.markdown("---")
    else:
        st.info("Aguardando arquivos...")

with t1: exibir(processar_base(f_sj, "ROSA"), df_citop_geral, "SAO JOAO", "sj")
with t2: exibir(processar_base(f_rs, "SAO JOAO"), df_citop_geral, "ROSA", "rs")
