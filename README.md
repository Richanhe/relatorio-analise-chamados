# 🤖 Automação SAP Solution Manager (SolMan)

Esta automação foi desenvolvida para buscar e baixar relatórios (DME) associados a incidentes no **SAP Solution Manager (SolMan)** de forma automática. Ela utiliza o **Playwright** para se conectar a uma instância ativa do Google Chrome via protocolo de depuração remota (CDP), reaproveitando a sessão e a autenticação do usuário já ativa.

---

## ⚙️ Pré-requisitos e Configuração do Chrome

Para que o script consiga interagir com o SAP SolMan, é necessário utilizar uma instância do Chrome já aberta com a porta de depuração habilitada. Isso elimina a necessidade de lidar com telas de login complexas e autenticações multifator (MFA) dentro do código.

### 1. Iniciar o Chrome em Modo Debug
Abra o **PowerShell** e execute o seguinte comando para abrir o Chrome na porta `9222`:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\temp\chrome-playwright"
```

> [!IMPORTANT]
> - Mantenha esta janela do Chrome aberta durante a execução da automação.
> - Faça login no SAP Solution Manager (SolMan) nesta janela específica antes de iniciar o script.
> - O script se conectará exatamente a essa aba ativa.

---

## 📁 Requisitos de Arquivos e Pastas

Para a execução correta do script, certifique-se de que os seguintes arquivos e diretórios existam na raiz do projeto:

*   **`incidentes.xlsx`**: Planilha contendo a lista de incidentes que serão processados.
*   **`relatorios/`**: Diretório que armazenará os arquivos DME baixados. *(O script criará o caminho automaticamente se necessário, mas certifique-se de ter permissões de escrita).*

---

## 🚀 Instalação e Execução

### 1. Instalar as Dependências
O projeto utiliza o **uv** para gerenciar o ambiente virtual e as dependências. Para sincronizar as dependências e preparar o ambiente virtual:

```bash
uv sync
```

Instale os navegadores do Playwright (caso necessário para o driver):
```bash
uv run playwright install
```

### 2. Executar o Script
Com o Chrome configurado e logado na página do SolMan, execute a automação usando o `uv run`:

```bash
uv run python main.py
```

---

## 🔍 Fluxo da Automação (`main.py`)

1.  **Conexão via CDP (Chrome DevTools Protocol)**: Liga-se ao Chrome rodando em `http://localhost:9222`.
2.  **Mapeamento de Frames**: Localiza a estrutura interna de iframes do SAP SolMan (`CRMApplicationFrame` -> `WorkAreaFrame1`).
3.  **Filtro e Busca**: Acessa a aba de incidentes, pesquisa pelo ID correspondente e clica no resultado correspondente.
4.  **Gerenciamento de Anexos (Show/Hide)**: Verifica dinamicamente se o painel de anexos está visível. Se estiver fechado, clica em "Show Attachments".
5.  **Captura e Download do Último DME**: Identifica o link mais recente que contém o texto "DME", lida com a nova aba pop-up que é aberta e aciona o download, salvando o arquivo na pasta `./relatorios`.

---

> [!TIP]
> **Processamento em Lote:** O script atual lê a planilha `incidentes.xlsx` utilizando `pandas` no início do código, mas realiza a busca de um ID estático para testes. Para processar todos os IDs da planilha, implemente um laço de repetição (`for index, row in ids.iterrows():`) sobre o fluxo de busca.
