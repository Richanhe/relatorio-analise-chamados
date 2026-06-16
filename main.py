from playwright.sync_api import sync_playwright
import pandas as pd
import os

ids = pd.read_excel("incidentes.xlsx")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(
        "http://localhost:9222"
    )
    context = browser.contexts[0]
    page = context.pages[0]

    # Salvando o caminho do frame em uma variável para facilitar a leitura
    work_area = page.locator('iframe[name="CRMApplicationFrame"]').content_frame.locator('#WorkAreaFrame1').content_frame

    work_area.locator(".th-menu2-arrow").click()
    work_area.get_by_role("link", name="Incidents").click()
    
    # Preenchendo a busca
    work_area.get_by_role("textbox", name="Enter the value of criterion Incident ID").click()
    work_area.get_by_role("textbox", name="Enter the value of criterion Incident ID").fill("8000066095")
    work_area.get_by_role("link", name="Search", description="Search", exact=True).click()
    
    # Clicando no resultado
    work_area.get_by_role("link", name="8000066095").click()

    # --- Lógica do Show/Hide Attachments ---
    show_btn = work_area.get_by_role("link", name="Show Attachments")
    hide_btn = work_area.get_by_role("link", name="Hide Attachments")

    # Espera até que UM DOS DOIS botões fique visível na tela
    show_btn.or_(hide_btn).wait_for(state="visible")

    # Se o botão de "Show Attachments" estiver visível, ele clica. 
    # Se o "Hide" estiver visível, ele ignora e segue o baile.
    if show_btn.is_visible():
        show_btn.click()

    page.wait_for_load_state("networkidle")
    todos_os_links = work_area.get_by_role("link")
    ultimo_dme = todos_os_links.filter(has_text="DME").last
    ultimo_dme.wait_for(state="visible")

    with page.expect_popup() as page2_info:
        ultimo_dme.click()
    page2 = page2_info.value
    page2.wait_for_load_state("domcontentloaded")

    iframe_download = page2.frames[1]

    with page2.expect_download() as download1_info:
        iframe_download.get_by_role("button", name="Baixar").click()

    download1 = download1_info.value
    nome_arquivo_1 = download1.suggested_filename

    caminho_relatorios = os.path.join(os.getcwd(), "relatorios")
    caminho_destino = os.path.join(caminho_relatorios, nome_arquivo_1)

    download1.save_as(caminho_destino)
    print(f"Download do último DME concluído e salvo em: {caminho_destino}")

    page2.close()