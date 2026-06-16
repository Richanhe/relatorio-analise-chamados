import os
import re
import pandas as pd
from pypdf import PdfReader

def extrair_dados_pdf(caminho_pdf):
    """
    Extrai as informações solicitadas de um relatório PDF do SAP SolMan (DME).
    """
    try:
        reader = PdfReader(caminho_pdf)
        texto_completo = ""
        for page in reader.pages:
            texto_completo += (page.extract_text() or "") + "\n"
    except Exception as e:
        print(f"Erro ao ler o arquivo {caminho_pdf}: {e}")
        return None

    dados = {
        "Arquivo": os.path.basename(caminho_pdf),
        "ID Solicitação": None,
        "Total Horas": None,
        "Conv Baseline Horas": None,
        "Conv Baseline Tickets": None,
        "Valor": None,
        "Horas por Grupo": None
    }

    # 1. ID da Solicitação
    nome_arquivo = os.path.basename(caminho_pdf)
    # Tenta achar um número de 10 dígitos que comece com 8 no nome do arquivo (padrão SAP SolMan: 8xxxxxxxxx)
    # Usamos lookaround (?<!\d) e (?!\d) ao invés de \b para suportar limites como underscores (_) sem casar com datas
    match_id_arq = re.search(r'(?<!\d)(8\d{9})(?!\d)', nome_arquivo)
    if match_id_arq:
        dados["ID Solicitação"] = match_id_arq.group(1)
    else:
        # Se não achou, tenta qualquer número de 10 dígitos no nome do arquivo
        match_id_arq_10 = re.search(r'(?<!\d)(\d{10})(?!\d)', nome_arquivo)
        if match_id_arq_10:
            dados["ID Solicitação"] = match_id_arq_10.group(1)

    # 2. Total Horas (ex: "Total de Horas – 98h")
    match_total_horas = re.search(r'Total\s+de\s+Horas\s*[-–—:]\s*([\d,]+\s*h(?:oras)?)', texto_completo, re.IGNORECASE)
    if match_total_horas:
        dados["Total Horas"] = match_total_horas.group(1).strip()

    # 3. Conversão Horas Baseline (ex: "Conversão horas baseline: 98,00horas" ou "Conversão baseline horas: 98h")
    match_conv_horas = re.search(
        r'Conversão\s+(?:de\s+)?(?:horas\s+baseline|baseline\s+horas)\s*:\s*([\d,\.]+\s*(?:h|horas)?)',
        texto_completo,
        re.IGNORECASE
    )
    if match_conv_horas:
        dados["Conv Baseline Horas"] = match_conv_horas.group(1).strip()

    # 4. Conversão Tickets Baseline (ex: "Conversão de tickets baseline: 5 tickets" ou "Conversão baseline tickets: 5 tks")
    match_conv_tickets = re.search(
        r'Conversão\s+(?:de\s+)?(?:tickets\s+baseline|baseline\s+tickets)\s*:\s*([\d,\.]+\s*(?:tickets|ticket|tks)?)',
        texto_completo,
        re.IGNORECASE
    )
    if match_conv_tickets:
        dados["Conv Baseline Tickets"] = match_conv_tickets.group(1).strip()

    # 5. Valor / Investimento (ex: "Investimento (em R$): R$ 10.000,00" ou "Investimento (em R$): R$ ")
    match_valor = re.search(r'Investimento\s*\(em\s*R\$\)\s*:\s*(.*)', texto_completo, re.IGNORECASE)
    if match_valor:
        val_extracted = match_valor.group(1).strip()
        # Se contiver números (mesmo com pontuação), extraímos o valor limpo, caso contrário tratamos como None
        val_numeros = re.search(r'([\d\.,]+)', val_extracted)
        if val_numeros:
            dados["Valor"] = f"R$ {val_numeros.group(1)}"
        else:
            dados["Valor"] = None

    # 6. Horas por Grupo (ex: "Total de Horas por Perfil: \n Desenvolvedor ABAP: 52h \n Funcional SD 46h")
    header_pattern = re.compile(r'(?:Total\s+de\s+)?Horas\s+por\s+(?:Perfil|Grupo|Cargo)\s*:', re.IGNORECASE)
    match_grupo = header_pattern.search(texto_completo)
    if match_grupo:
        start_pos = match_grupo.end()
        remaining_text = texto_completo[start_pos:]
        lines = remaining_text.split('\n')
        
        profiles = []
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            
            # Se bater com critérios de parada (início de nova seção), interrompe a leitura dos perfis
            if re.search(r'^(?:Critérios|Importante|\d+\.|---|História|Premissas|Faturamento|Aprovação)', line_strip, re.IGNORECASE):
                break
                
            # Verifica se tem padrão de Perfil: Horas (ex: "Desenvolvedor ABAP: 52h" ou "Funcional SD 46h")
            profile_match = re.search(
                r'^([a-zA-Záéíóúâêîôûãõç\s\-/(),.]+)[:\-\s]+(\d+\s*h(?:oras)?)',
                line_strip,
                re.IGNORECASE
            )
            if profile_match:
                p_name = profile_match.group(1).strip()
                p_hours = profile_match.group(2).strip()
                profiles.append(f"{p_name}: {p_hours}")
            else:
                if profiles:
                    break
        if profiles:
            dados["Horas por Grupo"] = ", ".join(profiles)
            
    return dados

def main():
    pasta_relatorios = "relatorios"
    if not os.path.exists(pasta_relatorios):
        print(f"Erro: A pasta '{pasta_relatorios}' não existe.")
        return

    # Listar todos os arquivos PDF na pasta
    arquivos = [os.path.join(pasta_relatorios, f) for f in os.listdir(pasta_relatorios) if f.lower().endswith(".pdf")]
    
    if not arquivos:
        print(f"Nenhum arquivo PDF encontrado na pasta '{pasta_relatorios}'.")
        return

    print(f"Encontrados {len(arquivos)} arquivos PDF para analisar.")
    
    lista_resultados = []
    for arq in arquivos:
        print(f"Analisando: {os.path.basename(arq)}...")
        resultado = extrair_dados_pdf(arq)
        if resultado:
            lista_resultados.append(resultado)

    if not lista_resultados:
        print("Nenhum dado pode ser extraido dos relatorios.")
        return

    # Criar DataFrame com os resultados
    df = pd.DataFrame(lista_resultados)
    
    # Ordenar colunas para exibição amigável
    colunas_ordenadas = ["ID Solicitação", "Arquivo", "Total Horas", "Conv Baseline Horas", "Conv Baseline Tickets", "Valor", "Horas por Grupo"]
    df = df[colunas_ordenadas]

    # Salvar em Excel
    caminho_saida = os.path.join(pasta_relatorios, "analise_relatorios.xlsx")
    try:
        df.to_excel(caminho_saida, index=False)
        print(f"\nAnalise concluida com sucesso! Resultados salvos em: {caminho_saida}")
    except Exception as e:
        print(f"Erro ao salvar arquivo Excel de resultados: {e}")

    # Exibir resultado no terminal
    print("\n--- RESUMO DA EXTRACO ---")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df.to_string(index=False))

if __name__ == "__main__":
    main()
