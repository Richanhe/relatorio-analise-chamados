from playwright.sync_api import sync_playwright
import pandas as pd
import os

# Garantir que a pasta de relatórios exista
os.makedirs("relatorios", exist_ok=True)

# Tenta carregar o arquivo Excel de incidentes
caminho_excel = "ids.xlsx"
if not os.path.exists(caminho_excel):
    print(f"Erro: O arquivo '{caminho_excel}' não foi encontrado.")
    exit(1)

df = pd.read_excel(caminho_excel)

# Identifica a coluna contendo os IDs
col_name = None
for col in df.columns:
    if 'incident' in str(col).lower() or 'id' in str(col).lower():
        col_name = col
        break

if col_name:
    raw_list = df[col_name].dropna().tolist()
else:
    raw_list = df.iloc[:, 0].dropna().tolist()

# Limpar e formatar IDs (removendo possíveis sufixos decimais .0 gerados pela leitura de números no pandas)
ids_list = []
for val in raw_list:
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    if val_str and val_str != "nan":
        ids_list.append(val_str)

if not ids_list:
    print("Nenhum ID de incidente encontrado na planilha para processamento.")
    exit(0)

print(f"Total de incidentes encontrados para processar: {len(ids_list)}")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(
        "http://localhost:9222"
    )
    context = browser.contexts[0]
    page = context.pages[0]

    # Salvando o caminho do frame em uma variável para facilitar a leitura
    work_area = page.locator('iframe[name="CRMApplicationFrame"]').content_frame.locator('#WorkAreaFrame1').content_frame

    for idx, incident_id in enumerate(ids_list, start=1):
        print(f"\n[{idx}/{len(ids_list)}] Iniciando busca do incidente: {incident_id}")
        
        try:
            # Navegar para a seção de Incidentes para limpar qualquer busca anterior
            work_area.locator(".th-menu2-arrow").click()
            work_area.get_by_role("link", name="Incidents").click()
            
            # Preenchendo a busca do SolMan
            work_area.get_by_role("textbox", name="Enter the value of criterion Incident ID").click()
            work_area.get_by_role("textbox", name="Enter the value of criterion Incident ID").fill(incident_id)
            work_area.get_by_role("link", name="Search", description="Search", exact=True).click()
            
            # Clicando no resultado da pesquisa correspondente ao ID.
            # Nota: O link possui o atributo aria-label="ID", o que sobrescreve o nome acessível (accessible name)
            # no Playwright, impedindo a busca direta por get_by_role("link", name=incident_id).
            # Para contornar isso, buscamos pelo atributo title ou pelo texto exato da tag 'a'.
            link_resultado = work_area.locator(f"a[title='{incident_id}']").or_(
                work_area.locator("a").get_by_text(incident_id, exact=True)
            ).first
            
            link_resultado.wait_for(state="visible", timeout=10000)
            link_resultado.click()
        
            # --- Lógica do Show/Hide Attachments ---
            show_btn = work_area.get_by_role("link", name="Show Attachments")
            hide_btn = work_area.get_by_role("link", name="Hide Attachments")
        
            # Espera até que um dos dois botões de anexos fique visível
            show_btn.or_(hide_btn).wait_for(state="visible", timeout=15000)
        
            # Se o botão de "Show Attachments" estiver visível, clica para exibir os anexos
            if show_btn.is_visible():
                show_btn.click()
        
            page.wait_for_load_state("networkidle")
            todos_os_links = work_area.get_by_role("link")
            ultimo_dme = todos_os_links.filter(has_text="DME").last
            ultimo_dme.wait_for(state="visible", timeout=10000)
        
            # Captura a abertura do popup ao clicar no link do DME
            with page.expect_popup() as page2_info:
                ultimo_dme.click()
            page2 = page2_info.value
            page2.wait_for_load_state("domcontentloaded")
        
            iframe_download = page2.frames[1]
        
            # Realiza o download do documento
            with page2.expect_download() as download1_info:
                iframe_download.get_by_role("button", name="Baixar").click()
        
            download1 = download1_info.value
            nome_arquivo_1 = download1.suggested_filename
        
            caminho_relatorios = os.path.join(os.getcwd(), "relatorios")
            caminho_destino = os.path.join(caminho_relatorios, nome_arquivo_1)
        
            download1.save_as(caminho_destino)
            print(f"Sucesso: Download do último DME concluído e salvo em: {caminho_destino}")
        
            page2.close()
            
        except Exception as e:
            print(f"Erro ao processar o incidente {incident_id}: {e}")
            # Tenta garantir o fechamento de possíveis janelas adicionais abertas para não travar o fluxo
            try:
                if 'page2' in locals() and not page2.is_closed():
                    page2.close()
            except Exception:
                pass
            continue