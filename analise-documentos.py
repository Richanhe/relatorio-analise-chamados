import os
import re
import shutil
import pandas as pd
import pytesseract
from PIL import Image
from pypdf import PdfReader

# Resolver o caminho do tesseract dinamicamente no Windows
def resolve_tesseract_path():
    paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "tesseract"

pytesseract.pytesseract.tesseract_cmd = resolve_tesseract_path()

def is_valid_profile_name(name):
    """
    Verifica se o nome do perfil contém pelo menos uma palavra-chave válida,
    evitando que nomes de pessoas ou textos de aprovação sejam interpretados como perfis.
    """
    name_upper = name.upper()
    
    # Palavras-chave longas que podem ser substrings (tamanho >= 4)
    substring_keywords = [
        'FUNCIONAL', 'DESENVOLVEDOR', 'ABAP', 'GESTAO', 'GESTÃO', 'PMO', 'ARQUITETO', 
        'CONSULTOR', 'BASIS', 'INTEGRACAO', 'INTEGRAÇÃO', 'FOMENTO', 'GRAOS', 'GRÃOS', 
        'COCUMORENAEUNN'
    ]
    # Palavras-chave curtas que devem ser palavras completas
    word_keywords = [
        'SD', 'MM', 'FI', 'CO', 'PP', 'WM', 'WEB', 'COE', 'ACM'
    ]
    
    if any(kw in name_upper for kw in substring_keywords):
        return True
        
    # Extrai todas as palavras do nome
    words = re.findall(r'\b[A-Z0-9]+\b', name_upper)
    if any(kw in words for kw in word_keywords):
        return True
        
    return False


def normalize_profile_name(name):
    """
    Normaliza os nomes dos perfis, limpando sujeiras e mapeando variações/erros comuns de OCR.
    """
    # Remove caracteres especiais, mantendo letras, espaços, barras e hifens
    name_clean = re.sub(r'[^a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-/(),.]', '', name)
    name_norm = re.sub(r'\s+', ' ', name_clean).strip().upper()
    
    if not name_norm:
        return ""
        
    # Tratamento de variações e erros comuns de OCR
    if any(x in name_norm for x in ['COE GA', 'COCUMORENAEUNN', 'FUNCIONAL', 'CONSULTOR FUNCIONAL', 'O FUNCIONAL']):
        # Mapeamento especial para os centros de custo e de processos
        if 'FI' in name_norm:
            return "Funcional FI"
        if 'SD' in name_norm:
            return "Funcional SD"
        if 'MM' in name_norm:
            return "Funcional MM"
        if 'ACM' in name_norm:
            return "Funcional ACM"
        if 'APPGR' in name_norm or 'GR' in name_norm:
            return "Funcional AppGraos"
        if 'FOMENTO' in name_norm:
            return "Funcional Fomento"
        return "Consultor Funcional"
        
    if any(x in name_norm for x in ['DESENVOLVEDOR', 'ABAP', 'SDK', 'WEB']):
        if 'WEB' in name_norm:
            return "Desenvolvedor WEB"
        return "Desenvolvedor ABAP" if 'ABAP' in name_norm else "Desenvolvedor"
        
    if any(x in name_norm for x in ['GESTAO', 'GESTÃO', 'PMO']):
        return "Gestão / PMO"
        
    if 'BASIS' in name_norm or 'INTEG' in name_norm:
        return "BASIS/Integração"
        
    return name_norm.title()

def find_macro_estimativa_page(reader):
    """
    Encontra o índice da página de Macro Estimativa com base no cabeçalho ou proximidade do investimento.
    """
    # Método 1: Busca pelo cabeçalho exato da seção de macro estimativa
    for idx, page in reversed(list(enumerate(reader.pages))):
        page_text = page.extract_text() or ""
        if "SUMÁRIO" in page_text.upper() or "SUMARIO" in page_text.upper():
            continue
        # Procurar por padrões como "6. Macro Estimativa" ou "8. Macro Estimativa"
        if re.search(r'\b\d+\s*\.\s*Macro\s+Estimativa\b', page_text, re.IGNORECASE):
            return idx

    # Método 2: Fallback para a busca genérica por "MACRO ESTIMATIVA"
    for idx, page in reversed(list(enumerate(reader.pages))):
        page_text = page.extract_text() or ""
        if "SUMÁRIO" in page_text.upper() or "SUMARIO" in page_text.upper():
            continue
        norm_text = re.sub(r'\s+', ' ', page_text.upper())
        if re.search(r'(?<!DOCUMENTO DE\s)MACRO\s+ESTIMATIVA', norm_text):
            return idx

    # Método 3: Busca a página anterior à seção de Investimento
    for idx, page in reversed(list(enumerate(reader.pages))):
        page_text = page.extract_text() or ""
        norm_text = re.sub(r'\s+', ' ', page_text.upper())
        if "INVESTIMENTO" in norm_text or "FORMATO DE INVESTIMENTO" in norm_text:
            if idx > 0:
                return idx - 1

    return None

def parse_ocr_profiles(ocr_text):
    """
    Analisa o texto extraído por OCR para identificar nomes de perfis e suas respectivas horas.
    """
    profiles = []
    lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    
    # Palavras que indicam que a linha NÃO é de perfil individual
    blacklist = [
        "total de horas", "total de horas por", "total horas", "importante", "esforco", "esforço", 
        "execucao", "execução", "contrato", "essas", "alteradas", "nivel", "nível", "precificacao", 
        "precificação", "bayer", "porto", "solman", "chamado", "cliente", "considera", "atividades", 
        "acompanhamento", "testes", "customizing", "especif", "desenvolvimento", "documentacao", 
        "documentação", "garantia", "hypercare", "planejamento"
    ]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. Identificar o número correspondente às horas na linha (ex: 208,00 ou 16,00 ou 78)
        num_match = re.search(r'\b(\d+[\.,]\d+|\d+)\b', line)
        if num_match:
            hours_str = num_match.group(1)
            start_idx, end_idx = num_match.span()
            profile_part = line[:start_idx].strip()
        else:
            # Fallback: verifica se a próxima linha é um número puro
            profile_part = line.split('|')[0].strip()
            hours_str = None
            if i + 1 < len(lines):
                next_line = lines[i+1]
                next_line_part = next_line.split('|')[0].strip()
                next_line_clean = re.sub(r'(?i)\s*(?:h|horas|hr|hrs)?\s*$', '', next_line_part).strip()
                if re.match(r'^[\d\.,]+$', next_line_clean):
                    hours_str = next_line_clean
                    i += 1 # Consome a próxima linha
            
        if not hours_str:
            i += 1
            continue
            
        # Limpar ruídos comuns do início do nome do perfil (ex: marcadores, tabelas)
        profile_part_clean = re.sub(r'^[:\s\-\|•\*\+o\u2022\u2610\u2611]+', '', profile_part).strip()
        profile_part_lower = profile_part_clean.lower()
        
        has_bl = any(x in profile_part_lower for x in blacklist)
        is_too_short = len(re.sub(r'[^a-zA-Z]', '', profile_part_clean)) < 2
        
        if not profile_part_clean or has_bl or is_too_short or not is_valid_profile_name(profile_part_clean):
            i += 1
            continue
            
        val_clean = hours_str.replace(',', '.')
        if '.' not in val_clean and len(val_clean) >= 3 and val_clean.endswith('00'):
            val_clean = val_clean[:-2] + '.' + val_clean[-2:]
            
        try:
            val_clean = re.sub(r'[^\d\.]', '', val_clean)
            hours_val = float(val_clean)
            if hours_val > 0:
                normalized_name = normalize_profile_name(profile_part_clean)
                if normalized_name:
                    profiles.append((normalized_name, hours_val))
        except ValueError:
            pass
            
        i += 1
        
    return profiles

def extrair_dados_ocr(caminho_pdf, page_index):
    """
    Extrai as imagens da página do PDF e executa OCR via pytesseract,
    aplicando múltiplos preprocessamentos (original, 2x escala cinza, 2x binarizado)
    para buscar total de horas e perfis de forma resiliente.
    """
    temp_dir = "temp_ocr_imgs_process"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        reader = PdfReader(caminho_pdf)
        if page_index >= len(reader.pages):
            return None, None
        
        page = reader.pages[page_index]
        images_data = []
        
        # Salva todas as imagens da página localmente primeiro
        for idx, img_obj in enumerate(page.images):
            img_path = os.path.join(temp_dir, f"temp_{idx}_{img_obj.name}")
            with open(img_path, "wb") as f:
                f.write(img_obj.data)
            images_data.append((img_path, img_obj.name))
            
        if not images_data:
            return None, None
            
        # Vamos gerar os textos completos para cada uma das 3 passagens de OCR
        text_orig_list = []
        text_gray_list = []
        text_bin_list = []
        
        for img_path, img_name in images_data:
            try:
                img = Image.open(img_path)
                
                # 1. OCR Original
                text_orig = pytesseract.image_to_string(img, lang="por+eng")
                text_orig_list.append(text_orig)
                
                # 2. Redimensiona 2x e escala cinza
                width, height = img.size
                img_resized = img.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
                img_gray = img_resized.convert('L')
                text_gray = pytesseract.image_to_string(img_gray, lang="por+eng")
                text_gray_list.append(text_gray)
                
                # 3. Binarização
                threshold = 127
                img_bin = img_gray.point(lambda p: 255 if p > threshold else 0)
                text_bin = pytesseract.image_to_string(img_bin, lang="por+eng")
                text_bin_list.append(text_bin)
            except Exception as e:
                print(f"Erro ao processar imagem {img_name}: {e}")
                
        # Combina os textos de todas as imagens para cada tipo de passagem
        passes = [
            ("original", "\n".join(text_orig_list)),
            ("gray", "\n".join(text_gray_list)),
            ("binarized", "\n".join(text_bin_list))
        ]
        
        pass_results = []
        all_totals = []
        
        for pass_name, pass_text in passes:
            # Extrai perfis e deduplica
            raw_profiles = parse_ocr_profiles(pass_text)
            profile_dict = {}
            for p_name, p_hours in raw_profiles:
                key = p_name.upper()
                if key not in profile_dict or p_hours > profile_dict[key][1]:
                    profile_dict[key] = (p_name, p_hours)
            deduped_profiles = list(profile_dict.values())
            sum_hours = sum(h for _, h in deduped_profiles)
            
            # Extrai total de horas
            total_val = None
            tot_match = re.search(r'TOTAL\s+DE\s+HORAS\s*\|?\s*([\d,\.]+)', pass_text, re.IGNORECASE)
            if tot_match:
                val_str = tot_match.group(1).replace(',', '.')
                val_str = re.sub(r'[^\d\.]', '', val_str)
                if val_str:
                    try:
                        total_val = float(val_str)
                        all_totals.append(total_val)
                    except ValueError:
                        pass
                        
            pass_results.append({
                "pass_name": pass_name,
                "profiles": deduped_profiles,
                "total": total_val,
                "sum": sum_hours
            })
            
        # Determinar qual passagem do OCR é a mais confiável usando heurísticas de soma
        best_pass = None
        
        # Heurística 1: a soma dos perfis bate exatamente com o total lido na mesma passagem
        for res in pass_results:
            if res["total"] is not None and abs(res["sum"] - res["total"]) < 0.1 and res["sum"] > 0:
                best_pass = res
                break
                
        # Heurística 2: a soma dos perfis bate com algum total lido em qualquer passagem
        if not best_pass and all_totals:
            for res in pass_results:
                if res["sum"] > 0 and any(abs(res["sum"] - t) < 0.1 for t in all_totals):
                    best_pass = res
                    best_pass["total"] = next(t for t in all_totals if abs(res["sum"] - t) < 0.1)
                    break
                    
        # Heurística 3: escolhe a passagem com soma mais próxima do maior total lido
        if not best_pass and all_totals:
            max_total = max(all_totals)
            best_diff = float('inf')
            for res in pass_results:
                if res["sum"] > 0:
                    diff = abs(res["sum"] - max_total)
                    if diff < best_diff:
                        best_diff = diff
                        best_pass = res
            if best_pass:
                best_pass["total"] = max_total
                
        # Heurística 4: escolhe a passagem com a maior soma acumulada (evita perder dados)
        if not best_pass:
            best_pass = max(pass_results, key=lambda x: x["sum"])
            
        if best_pass and best_pass["profiles"]:
            final_total = best_pass["total"] if best_pass["total"] is not None else best_pass["sum"]
            total_horas_str = f"{int(final_total)} h" if final_total.is_integer() else f"{final_total} h"
            grupo_str = ", ".join(f"{name}: {int(h) if h.is_integer() else h} h" for name, h in best_pass["profiles"])
            return total_horas_str, grupo_str
            
    except Exception as e:
        print(f"Erro no processamento de OCR para {os.path.basename(caminho_pdf)}: {e}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    return None, None

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
    match_id_arq = re.search(r'(?<!\d)(8\d{9})(?!\d)', nome_arquivo)
    if match_id_arq:
        dados["ID Solicitação"] = match_id_arq.group(1)
    else:
        # Se não achou, tenta qualquer número de 10 dígitos no nome do arquivo
        match_id_arq_10 = re.search(r'(?<!\d)(\d{10})(?!\d)', nome_arquivo)
        if match_id_arq_10:
            dados["ID Solicitação"] = match_id_arq_10.group(1)
        else:
            # Fallback para busca no texto: "Número da Solicitação: 8000066095"
            match_id_txt = re.search(r'Número\s+da\s+Solicitação\s*:\s*(\d+)', texto_completo, re.IGNORECASE)
            if match_id_txt:
                dados["ID Solicitação"] = match_id_txt.group(1)

    # 2. Total Horas (ex: "Total de Horas – 98h", "Macro Esforço Total: 48h")
    match_total_horas = re.search(
        r'(?:Total\s+de\s+Horas|Macro\s+Esforço\s+Total|Esforço\s+Total)\s*[-–—:]?\s*([\d,\.]+(?:\s*(?:h(?:oras)?|hr?s?))?)',
        texto_completo,
        re.IGNORECASE
    )
    if match_total_horas:
        val = match_total_horas.group(1).strip()
        val_num = re.search(r'([\d\.,]+)', val)
        if val_num:
            dados["Total Horas"] = f"{val_num.group(1)} h"
        else:
            dados["Total Horas"] = val

    # 3. Conversão Horas Baseline (ex: "Conversão horas baseline: 98,00horas")
    match_conv_horas = re.search(
        r'Conversão\s+(?:de\s+)?(?:horas\s+baseline|baseline\s+horas)\s*:\s*([\d,\.]+(?:\s*(?:h(?:oras)?|hr?s?))?)',
        texto_completo,
        re.IGNORECASE
    )
    if not match_conv_horas:
        # Fallback para o novo formato em tabela
        match_conv_horas = re.search(
            r'Conversão\s+de\s+Horas\s+Baseline\s+([\d,\.]+(?:\s*(?:h(?:oras)?|hr?s?))?)',
            texto_completo,
            re.IGNORECASE
        )
    if match_conv_horas:
        val_conv = match_conv_horas.group(1).strip()
        val_conv_num = re.search(r'([\d\.,]+)', val_conv)
        if val_conv_num:
            dados["Conv Baseline Horas"] = f"{val_conv_num.group(1)} h"
        else:
            dados["Conv Baseline Horas"] = val_conv

    # 4. Conversão Tickets Baseline (ex: "Conversão de tickets baseline: 5 tickets" ou "Conversão baseline tickets: 5 tks")
    match_conv_tickets = re.search(
        r'Conversão\s+(?:de\s+)?(?:tickets\s+baseline|baseline\s+tickets)\s*[-–—:]?\s*([\d,\.]+(?:\s*(?:tickets|ticket|tks))?)',
        texto_completo,
        re.IGNORECASE
    )
    if match_conv_tickets:
        val_tk = match_conv_tickets.group(1).strip()
        val_tk_num = re.search(r'([\d\.,]+)', val_tk)
        if val_tk_num:
            dados["Conv Baseline Tickets"] = f"{val_tk_num.group(1)} tickets"
        else:
            dados["Conv Baseline Tickets"] = val_tk

    # 5. Valor / Investimento (ex: "Investimento (em R$): R$ 10.000,00" ou "Investimento (em R$): R$ ")
    match_valor = re.search(r'Investimento\s*\(em\s*R\$\)\s*:\s*(.*)', texto_completo, re.IGNORECASE)
    if not match_valor:
        # Fallback para o novo formato em tabela (ex: "☐ Investimento extracontrato (em R$) R$ 6.641,43")
        match_valor = re.search(
            r'Investimento\s*(?:extracontrato\s*)?\(em\s*R\$\)\s*(.*)',
            texto_completo,
            re.IGNORECASE
        )
    if match_valor:
        val_extracted = match_valor.group(1).strip()
        val_numeros = re.search(r'([\d\.,]+)', val_extracted)
        if val_numeros:
            dados["Valor"] = f"R$ {val_numeros.group(1)}"
        else:
            dados["Valor"] = None

    # 6. Horas por Grupo (ex: "Total de Horas por Perfil: \n Desenvolvedor ABAP: 52h \n Funcional SD 46h")
    header_pattern = re.compile(r'(?:Total\s+de\s+)?Horas\s+por\s+(?:Perfil|Grupo|Cargo)\s*:', re.IGNORECASE)
    match_grupo = header_pattern.search(texto_completo)
    
    profiles = []
    
    if match_grupo:
        start_pos = match_grupo.end()
        remaining_text = texto_completo[start_pos:]
        lines = remaining_text.split('\n')
        
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            
            # Se bater com critérios de parada (início de nova seção), interrompe a leitura dos perfis
            if re.search(r'^(?:Critérios|Importante|\d+\.|---|História|Premissas|Faturamento|Aprovação)', line_strip, re.IGNORECASE):
                break
                
            # Permite marcadores no início, decimais e sufixos opcionais
            profile_match = re.search(
                r'^\s*[\u2022•\-\*o]?\s*([a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s\-/(),.]+)[:\-–—\s\u2013\u2014]+\s*(\d+(?:[\.,]\d+)?(?:\s*(?:h(?:oras)?|hr?s?))?)',
                line_strip,
                re.IGNORECASE
            )
            if profile_match:
                p_name = profile_match.group(1).strip()
                p_hours = profile_match.group(2).strip()
                if is_valid_profile_name(p_name):
                    hours_num_match = re.search(r'([\d\.,]+)', p_hours)
                    if hours_num_match:
                        p_hours = f"{hours_num_match.group(1)} h"
                    normalized_name = normalize_profile_name(p_name)
                    if normalized_name:
                        profiles.append(f"{normalized_name}: {p_hours}")
            else:
                if profiles:
                    break
                    
    # Se não conseguimos perfis via cabeçalho estruturado, tenta uma varredura geral por padrão "Esforço..."
    if not profiles:
        general_matches = re.findall(
            r'(?:Esforço|Perfil)\s+([a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s\-/(),.]+?)\s*[:\-–—\s\u2013\u2014|]+\s*(\d+(?:[\.,]\d+)?\s*(?:h(?:oras)?|hr?s?))',
            texto_completo,
            re.IGNORECASE
        )
        for p_name, p_hours in general_matches:
            p_name = p_name.strip()
            p_hours = p_hours.strip()
            p_name_lower = p_name.lower()
            blacklist_words = ["total", "importante", "esforço", "esforco", "atividades", "testes"]
            if any(x in p_name_lower for x in blacklist_words) or len(p_name) < 2 or not is_valid_profile_name(p_name):
                continue
            normalized_name = normalize_profile_name(p_name)
            if normalized_name:
                hours_num_match = re.search(r'([\d\.,]+)', p_hours)
                if hours_num_match:
                    p_hours = f"{hours_num_match.group(1)} h"
                profiles.append(f"{normalized_name}: {p_hours}")
            
    if profiles:
        # Remover duplicados mantendo a ordem
        seen = set()
        deduped = []
        for p in profiles:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        dados["Horas por Grupo"] = ", ".join(deduped)

    # Se não conseguimos extrair Total Horas ou Horas por Grupo via texto, tentamos OCR na página de Macro Estimativa
    if not dados["Total Horas"] or not dados["Horas por Grupo"]:
        page_index_ocr = find_macro_estimativa_page(reader)
        if page_index_ocr is not None:
            total_ocr, grupo_ocr = extrair_dados_ocr(caminho_pdf, page_index_ocr)
            # Fallback para a página seguinte (caso a tabela tenha sido empurrada por quebra de página)
            if (not total_ocr or not grupo_ocr) and page_index_ocr + 1 < len(reader.pages):
                total_ocr_next, grupo_ocr_next = extrair_dados_ocr(caminho_pdf, page_index_ocr + 1)
                if total_ocr_next or grupo_ocr_next:
                    total_ocr, grupo_ocr = total_ocr_next, grupo_ocr_next
            
            if total_ocr and not dados["Total Horas"]:
                dados["Total Horas"] = total_ocr
            if grupo_ocr and not dados["Horas por Grupo"]:
                dados["Horas por Grupo"] = grupo_ocr

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
