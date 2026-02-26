import streamlit as st
import pandas as pd
from datetime import timedelta
import io
from io import StringIO

# ==================================================
# CONFIGURAÇÃO DA PÁGINA
# ==================================================
st.set_page_config(
    page_title="Viagens sem Reforço",
    page_icon="🚌",
    layout="wide"
)

if "validacoes" not in st.session_state:
    st.session_state.validacoes = {}

# CSS para Boxes e Botões
st.markdown("""
    <style>
    .pc1-box { padding: 8px; border-radius: 5px; background-color: #FFA500; color: white; font-weight: bold; display: inline-block; width: 250px; }
    .pc2-box { padding: 8px; border-radius: 5px; background-color: #1E90FF; color: white; font-weight: bold; display: inline-block; width: 250px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚌 Sistema de Gestão de Viagens")

# ==================================================
# BARRA LATERAL
# ==================================================
st.sidebar.header("📁 Upload de Arquivos Base")
file_sj = st.sidebar.file_uploader("Planilha SÃO JOÃO", type=["xlsx", "csv"])
file_rosa = st.sidebar.file_uploader("Planilha ROSA", type=["xlsx", "csv"])

if st.sidebar.button("🗑️ Limpar Tudo"):
    st.session_state.validacoes = {}
    st.rerun()

# ==================================================
# FUNÇÕES DE PROCESSAMENTO
# ==================================================
def processar_dados(uploaded_file, termo_para_ignorar):
    if uploaded_file is None: return None
    
    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        try:
            df = pd.read_csv(uploaded_file, sep=";", encoding="cp1252", engine="python")
        except:
            df = pd.read_csv(uploaded_file, sep=",", encoding="cp1252", engine="python")

    if df.shape[1] < 15: return None

    df = df.iloc[:, [0, 1, 3, 6, 14]]
    df.columns = ["empresa", "linha", "sentido", "atividade", "inicio_programado"]

    df["empresa"] = df["empresa"].astype(str).str.upper()
    df = df[~df["empresa"].str.contains(termo_para_ignorar, na=False)]
    
    df["linha"] = df["linha"].astype(str).str.strip()
    df["sentido"] = df["sentido"].astype(str).str.lower().str.strip()
    df["atividade"] = df["atividade"].astype(str).str.lower().str.strip()
    df["inicio_programado"] = pd.to_datetime(df["inicio_programado"], errors="coerce")
    
    df = df[df["sentido"] != "ocioso"]
    
    nao_realizadas = df[df["atividade"] == "não realizada"]
    reforcos = df[df["atividade"] == "reforço"]

    falhas = []
    for (linha, sentido), grupo_nr in nao_realizadas.groupby(["linha", "sentido"]):
        grupo_ref = reforcos[(reforcos["linha"] == linha) & (reforcos["sentido"] == sentido)].sort_values("inicio_programado").copy()
        grupo_ref["usado"] = False
        
        for _, nr in grupo_nr.iterrows():
            candidatos = grupo_ref[(~grupo_ref["usado"]) & (abs(grupo_ref["inicio_programado"] - nr["inicio_programado"]) <= timedelta(minutes=15))]
            if candidatos.empty:
                falhas.append(nr)
            else:
                grupo_ref.loc[candidatos.index[0], "usado"] = True

    return pd.DataFrame(falhas)

# ==================================================
# PROCESSAMENTO DOS DADOS E REMOÇÃO DE DUPLICATAS
# ==================================================
df_sj_final = processar_dados(file_sj, "ROSA")
df_rosa_final = processar_dados(file_rosa, "SAO JOAO")

lista_consolidada = []
if isinstance(df_sj_final, pd.DataFrame) and not df_sj_final.empty:
    lista_consolidada.append(df_sj_final)
if isinstance(df_rosa_final, pd.DataFrame) and not df_rosa_final.empty:
    lista_consolidada.append(df_rosa_final)

# CONSOLIDAÇÃO COM LIMPEZA DE DUPLICATAS
if lista_consolidada:
    df_para_exportar = pd.concat(lista_consolidada)
    # Remove duplicatas entre SJ e ROSA (mesma linha, sentido e hora)
    df_para_exportar = df_para_exportar.drop_duplicates(subset=["linha", "sentido", "inicio_programado"])
    # Ordena por horário
    df_para_exportar = df_para_exportar.sort_values(by="inicio_programado")
else:
    df_para_exportar = pd.DataFrame()

# ==================================================
# INTERFACE EM ABAS
# ==================================================
tab1, tab2, tab3 = st.tabs(["🏛️ SÃO JOÃO", "🌹 ROSA", "🔍 AUDITORIA FINAL"])

def exibir_resultados(df_resultado, prefixo):
    if isinstance(df_resultado, pd.DataFrame):
        if df_resultado.empty:
            st.success("✅ Nenhuma falha encontrada.")
        else:
            for linha in sorted(df_resultado["linha"].unique()):
                st.markdown(f"### 🚍 Linha {linha}")
                df_filtrado = df_resultado[df_resultado["linha"] == linha]
                for _, row in df_filtrado.iterrows():
                    h = row["inicio_programado"].strftime("%H:%M")
                    pc = "PC1" if row["sentido"] == "ida" else "PC2"
                    id_v = f"{prefixo}_{linha}_{h}_{pc}"
                    st.markdown(f"**🕒 {h}**")
                    cor = "pc1-box" if pc == "PC1" else "pc2-box"
                    st.markdown(f'<div class="{cor}">{pc} — Não Realizada</div>', unsafe_allow_html=True)
                    
                    if id_v in st.session_state.validacoes:
                        if st.button(f"✅ Realizada (e-CITOP)", key=id_v, type="primary"):
                            del st.session_state.validacoes[id_v]
                            st.rerun()
                    else:
                        if st.button(f"Confirmar no e-CITOP", key=id_v):
                            st.session_state.validacoes[id_v] = True
                            st.rerun()
                st.markdown("---")

with tab1:
    exibir_resultados(df_sj_final, "sj")

with tab2:
    exibir_resultados(df_rosa_final, "rosa")

# Lógica de Exportação Lateral
if not df_para_exportar.empty:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Exportar Relatório")
    df_download = df_para_exportar.copy()
    df_download["PC"] = df_download["sentido"].apply(lambda x: "PC1" if x == "ida" else "PC2")
    df_download["horario"] = df_download["inicio_programado"].dt.strftime("%H:%M")
    df_download = df_download[["linha", "sentido", "PC", "horario"]]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_download.to_excel(writer, index=False, sheet_name='Nao_Realizadas')
    
    st.sidebar.download_button(
        label="Baixar Planilha de Falhas",
        data=output.getvalue(),
        file_name="viagens_nao_realizadas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ==================================================
# ABA 3: AUDITORIA (CONVERSÃO E CONFRONTO)
# ==================================================
with tab3:
    st.header("🔍 Auditoria Final")
    
    file_auditoria = st.file_uploader("Suba o arquivo do e-CITOP", type=["txt", "csv"])
    
    if file_auditoria and not df_para_exportar.empty:
        try:
            raw = file_auditoria.read().decode('latin-1')
            clean_lines = [l for l in raw.splitlines() if ';' in l and not l.strip().startswith('[source')]
            df_ext = pd.read_csv(StringIO("\n".join(clean_lines)), sep=";", engine='python', dtype=str, header=0)
            
            df_aux = pd.DataFrame({
                 "col_linha": df_ext.iloc[:, 4].astype(str).str.strip().str.lstrip('0'),
                 "col_term": df_ext.iloc[:, 6].astype(str).str.strip(),
                 "col_saida": df_ext["Data Hora Saída Terminal"].astype(str).str.strip(),
                 "col_inicio": df_ext["Data Hora Início"].astype(str).str.strip(),
                 "col_passageiros": pd.to_numeric(df_ext["Passageiros"], errors="coerce").fillna(0)
            })

            def extrair_hhmm(valor):
                try:
                    dt = pd.to_datetime(valor, errors='coerce')
                    return dt.strftime("%H:%M") if pd.notna(dt) else None
                except:
                    return None

            criticas = []
            for _, falha in df_para_exportar.iterrows():
                l_site = str(falha["linha"]).strip().lstrip('0')
                pc_site = "1" if falha["sentido"] == "ida" else "2"
                h_site_str = falha["inicio_programado"].strftime("%H:%M")
                h_site_obj = pd.to_datetime(h_site_str, format="%H:%M")

                matches_linha = df_aux[(df_aux["col_linha"] == l_site) & (df_aux["col_term"] == pc_site)]

                sucesso = False
                hora_real_encontrada = "---"

                for _, reg in matches_linha.iterrows():

                    hora_usada = None
                    
                    # 1️⃣ PRIORIDADE → Data Hora Saída Terminal
                    if reg["col_saida"] and reg["col_saida"].lower() != "nan":
                        hora_usada = extrair_hhmm(reg["col_saida"])
                    
                    # 2️⃣ SE ESTIVER VAZIA → usar Data Hora Início
                    else:
                        if reg["col_passageiros"] >= 1:
                            hora_usada = extrair_hhmm(reg["col_inicio"])
                        else:
                            # Passageiros zerado = viagem não realizada
                            continue
                
                    if hora_usada:
                        h_ext_obj = pd.to_datetime(hora_usada, format="%H:%M")
                        diff = abs((h_ext_obj - h_site_obj).total_seconds() / 60)
                
                        if diff <= 10:
                            sucesso = True
                            hora_real_encontrada = hora_usada
                            break

                criticas.append({
                    "Linha": falha["linha"],
                    "Programado": h_site_str,
                    "PC": f"PC{pc_site}",
                    "Status": "✅ CONSTA NO E-CITOP" if sucesso else "🚨 NÃO REALIZADA",
                    "Hora Real": hora_real_encontrada
                })

            # EXIBIÇÃO E FILTRO
            df_final = pd.DataFrame(criticas)

            st.subheader("📊 Filtrar Resultados")
            opcoes_linhas = sorted(df_final["Linha"].unique())
            
            selecionar_tudo = st.checkbox("Selecionar todas as linhas")

            linhas_selecionadas = st.multiselect(
                "Pesquise ou selecione as linhas:", 
                options=opcoes_linhas, 
                default=opcoes_linhas if selecionar_tudo else []
            )
            
            df_exibicao = df_final[df_final["Linha"].isin(linhas_selecionadas)]
            
            def colorir_status(val):
                color = '#d4edda' if "CONSTA" in val else '#f8d7da'
                return f'background-color: {color}'

            st.dataframe(df_exibicao.style.applymap(colorir_status, subset=['Status']), use_container_width=True)
            
            csv = df_final.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button("📥 Baixar Relatório de Auditoria Completo", csv, "auditoria.csv")

        except Exception as e:
            st.error(f"Erro ao processar: {e}")

