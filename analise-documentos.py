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

def parse_ocr_profiles(ocr_text):
    """
    Analisa o texto extraído por OCR para identificar nomes de perfis e suas respectivas horas.
    """
    profiles = []
    lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    
    # Palavras-chave comuns para identificar linhas de perfil (como palavras inteiras)
    keywords_patterns = [
        r'\bfuncional\b', r'\bdesenvolvedor\b', r'\babap\b', r'\bsd\b', r'\bmm\b', 
        r'\bfi\b', r'\bco\b', r'\bpp\b', r'\bwm\b', r'\bweb\b', r'\bgestao\b', r'\bgestão\b',
        r'\bpmo\b', r'\barquiteto\b', r'\bconsultor\b', r'\bespecificas\b', r'\bespecíficas\b'
    ]
    
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
        
        # Se a linha contiver o delimitador de coluna |, separa o perfil/horas da descrição
        parts = line.split('|')
        profile_part = parts[0].strip()
        profile_part_lower = profile_part.lower()
        
        has_kw = any(re.search(pat, profile_part_lower) for pat in keywords_patterns)
        has_bl = any(x in profile_part_lower for x in blacklist)
        is_profile = has_kw and not has_bl
        
        if is_profile:
            profile_name = profile_part
            # Tenta encontrar número na própria linha (ex: "CONSULTOR FUNCIONAL 56,00")
            num_match = re.search(r'(\d+[\.,]\d+|\d+)', profile_part)
            if num_match:
                hours_str = num_match.group(1)
                # Remove o número e sujeiras do nome do perfil
                profile_name = re.sub(r'[\d\.,\|\(\)\-\u2013\u2014\?\*]+', '', profile_name).strip()
            else:
                # Se não tem número, verifica se a próxima linha é um número puro (tabela em coluna simples)
                hours_str = None
                if i + 1 < len(lines):
                    next_line = lines[i+1]
                    next_line_part = next_line.split('|')[0].strip()
                    next_line_clean = re.sub(r'(?i)\s*(?:h|horas|hr|hrs)?\s*$', '', next_line_part).strip()
                    if re.match(r'^[\d\.,]+$', next_line_clean):
                        hours_str = next_line_clean
                        i += 1 # Avança o índice
            
            if hours_str:
                val_clean = hours_str.replace(',', '.')
                # Corrige possíveis erros de leitura de decimal sem pontuação (ex: 400 -> 4.00)
                if '.' not in val_clean and len(val_clean) >= 3 and val_clean.endswith('00'):
                    val_clean = val_clean[:-2] + '.' + val_clean[-2:]
                
                try:
                    val_clean = re.sub(r'[^\d\.]', '', val_clean)
                    hours_val = float(val_clean)
                    if hours_val > 0:
                        profile_name = re.sub(r'^[:\s\-\|]+|[:\s\-\|]+$', '', profile_name).strip()
                        if profile_name:
                            profiles.append((profile_name, hours_val))
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
        all_extracted = []
        total_hours_values = []
        
        for idx, img_obj in enumerate(page.images):
            img_path = os.path.join(temp_dir, f"temp_{idx}_{img_obj.name}")
            with open(img_path, "wb") as f:
                f.write(img_obj.data)
            
            try:
                img = Image.open(img_path)
                
                # 1. OCR Original
                text_orig = pytesseract.image_to_string(img, lang="por+eng")
                all_extracted.extend(parse_ocr_profiles(text_orig))
                
                # 2. Preprocessamento: Redimensiona 2x e converte para escala de cinza
                width, height = img.size
                img_resized = img.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
                img_gray = img_resized.convert('L')
                
                text_gray = pytesseract.image_to_string(img_gray, lang="por+eng")
                all_extracted.extend(parse_ocr_profiles(text_gray))
                
                # 3. Preprocessamento: Binarização (Preto e Branco puro)
                threshold = 127
                img_bin = img_gray.point(lambda p: 255 if p > threshold else 0)
                text_bin = pytesseract.image_to_string(img_bin, lang="por+eng")
                all_extracted.extend(parse_ocr_profiles(text_bin))
                
                # Busca pela linha "TOTAL DE HORAS" em todas as leituras OCR
                for txt in [text_orig, text_gray, text_bin]:
                    tot_match = re.search(r'TOTAL\s+DE\s+HORAS\s*\|?\s*([\d,\.]+)', txt, re.IGNORECASE)
                    if tot_match:
                        val_str = tot_match.group(1).replace(',', '.')
                        val_str = re.sub(r'[^\d\.]', '', val_str)
                        if val_str:
                            try:
                                total_hours_values.append(float(val_str))
                            except ValueError:
                                pass
                                
            except Exception as e:
                print(f"Erro ao processar imagem {img_obj.name}: {e}")
                
        # Deduplicar perfis limpando caracteres de sujeira e mantendo o maior valor de horas
        profile_dict = {}
        for p_name, p_hours in all_extracted:
            # Mantém apenas letras, espaços e parênteses/hifens/barras/pontos para evitar ruídos de OCR
            p_name_clean = re.sub(r'[^a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-/(),.]', '', p_name)
            p_name_norm = re.sub(r'\s+', ' ', p_name_clean).strip()
            if not p_name_norm:
                continue
            
            key = p_name_norm.upper()
            if key not in profile_dict or p_hours > profile_dict[key][1]:
                profile_dict[key] = (p_name_norm, p_hours)
                
        deduped_profiles = [val for val in profile_dict.values()]
        
        if deduped_profiles:
            # Resolve o total de horas
            total_hours_from_row = max(total_hours_values) if total_hours_values else None
            calculated_sum = sum(h for _, h in deduped_profiles)
            
            final_total = total_hours_from_row if total_hours_from_row else calculated_sum
            total_horas_str = f"{int(final_total)} h" if final_total.is_integer() else f"{final_total} h"
            
            grupo_str = ", ".join(f"{name}: {int(h) if h.is_integer() else h} h" for name, h in deduped_profiles)
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
    if not match_conv_horas:
        # Fallback para o novo formato em tabela (ex: "☐ Conversão de Horas Baseline 29.72hr")
        match_conv_horas = re.search(
            r'Conversão\s+de\s+Horas\s+Baseline\s+([\d,\.]+\s*(?:h|horas|hr|hrs)?)',
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
                
            # Verifica se tem padrão de Perfil: Horas (ex: "Desenvolvedor ABAP: 52h" ou "Funcional (ACM) – 56 horas")
            # Inclui suporte a traços longos (en dash \u2013, em dash \u2014) como separadores
            profile_match = re.search(
                r'^([a-zA-Záéíóúâêîôûãõç\s\-/(),.]+)[:\-–—\s\u2013\u2014]+(\d+\s*h(?:oras)?)',
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

    # Se não conseguimos extrair Total Horas ou Horas por Grupo via texto, tentamos OCR na página de Macro Estimativa
    if not dados["Total Horas"] or not dados["Horas por Grupo"]:
        page_index_ocr = None
        # Varre o PDF de trás para frente
        for idx, page in reversed(list(enumerate(reader.pages))):
            page_text = page.extract_text() or ""
            
            # Se for a página de sumário/índice, ignora
            if "SUMÁRIO" in page_text.upper() or "SUMARIO" in page_text.upper():
                continue
                
            # Normaliza espaços
            norm_text = re.sub(r'\s+', ' ', page_text.upper())
            # Busca por "MACRO ESTIMATIVA" que não seja parte do cabeçalho "DOCUMENTO DE MACRO ESTIMATIVA"
            if re.search(r'(?<!DOCUMENTO DE\s)MACRO\s+ESTIMATIVA', norm_text):
                page_index_ocr = idx
                break
        
        if page_index_ocr is not None:
            total_ocr, grupo_ocr = extrair_dados_ocr(caminho_pdf, page_index_ocr)
            if total_ocr:
                dados["Total Horas"] = total_ocr
            if grupo_ocr:
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
