# Case AI Dev — Asset Servicing / Eventos Corporativos

Agente para leitura e interpretação de avisos aos acionistas em formatos heterogêneos (PDF nativo, texto puro e documentos digitalizados), produzindo um registro estruturado, validado e auditável para cada documento processado.

O objetivo do projeto é extrair eventos corporativos, validar as informações obtidas utilizando ferramentas auxiliares (tool calling), atribuir níveis de confiança aos campos extraídos e encaminhar automaticamente para revisão humana apenas os casos que realmente apresentem incerteza relevante.

---

# Escolha do provider de LLM

O projeto foi desenvolvido de forma que a lógica de extração não dependa de um modelo específico.

Toda a comunicação com o modelo ocorre através da interface `LLMProvider` (`src/providers/base.py`), permitindo trocar o backend apenas alterando variáveis de ambiente.

Providers disponíveis:

* anthropic (default)
* openai
* ollama (execução local)

Exemplo:

```bash
LLM_PROVIDER=anthropic
LLM_PROVIDER=openai
LLM_PROVIDER=ollama
```

Também é possível definir explicitamente o modelo:

```bash
LLM_MODEL=qwen3.5
```

---

## Utilizando Ollama

Para execução local:

```bash
ollama pull qwen2.5
```

ou

```bash
ollama pull llama3.1
```

Depois:

```bash
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5

python run.py
```

O provider Ollama utiliza o endpoint compatível com a API OpenAI exposto localmente pelo Ollama.

A integração é transparente para o restante da aplicação.

A principal diferença entre os modelos locais não está na integração, mas na qualidade da aderência ao tool calling. Alguns modelos menores tendem a ignorar chamadas de função ou produzir argumentos inconsistentes, aumentando artificialmente a quantidade de documentos enviados para revisão humana.

Durante os testes locais foram utilizados principalmente modelos da família Qwen.

---

# Instalação

Instalar dependências:

```bash
pip install -r requirements.txt
```

Executar:

```bash
python run.py
```

Arquivos gerados:

```text
output/
├── *.json
└── exceptions_report.md
```

---

# OCR e tratamento de documentos digitalizados

Durante os testes foi identificado que o documento:

```text
07_telecom_norte_jcp_SCAN.pdf
```

não possuía texto pesquisável.

A extração tradicional utilizando `pdfplumber` retornava conteúdo vazio, tornando necessária uma etapa de OCR.

A primeira implementação utilizou:

```text
pdf2image
+
pytesseract
```

Essa abordagem funcionava, mas dependia da instalação do Poppler.

Em ambiente Windows, a ausência dessa dependência gerava erros como:

```text
Unable to get page count. Is poppler installed and in PATH?
```

Embora fosse possível resolver isso documentando a instalação do Poppler, optei por simplificar o fluxo e reduzir dependências externas.

A implementação final utiliza:

```text
PyMuPDF (fitz)
+
Tesseract OCR
```

Fluxo:

```text
PDF
 ↓
PyMuPDF
 ↓
Imagem em memória
 ↓
Tesseract OCR
 ↓
Texto extraído
```

Vantagens:

* elimina dependência do Poppler;
* simplifica a configuração do ambiente;
* reduz problemas em Windows;
* melhora a portabilidade do projeto.

---

## Instalação do Tesseract

Foi utilizado o build para Windows disponibilizado pela comunidade UB Mannheim:

https://github.com/UB-Mannheim/tesseract/wiki

Além da instalação do executável, é necessário instalar os dados do idioma português.

Para evitar dependência do PATH do sistema operacional, o projeto permite configurar explicitamente o executável através da variável:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Caso o OCR falhe ou retorne conteúdo insuficiente, o documento é encaminhado para revisão humana em vez de gerar informações não verificadas.

---

# Arquitetura

```text
documentos/*.pdf
      │
      ▼
src/ingestion.py
      │
      ├─ texto nativo (pdfplumber)
      ├─ texto puro (fallback)
      ├─ OCR (PyMuPDF + Tesseract)
      └─ indisponível
      │
      ▼
src/extraction.py
      │
      ├─ agente com tool calling
      │
      ├─ lookup_golden_record
      ├─ check_date_coherence
      ├─ check_value_coherence
      └─ submit_registro
      │
      ▼
src/schema.py
      │
      ▼
src/confidence.py
      │
      ▼
output/*.json
exceptions_report.md
```

---

# Por que utilizar um agente com tool calling?

Uma abordagem baseada apenas em prompt e retorno direto de JSON seria suficiente para extração simples.

Entretanto, o objetivo do case é demonstrar validação explícita.

O agente:

1. extrai informações do documento;
2. consulta a base de referência;
3. valida datas;
4. valida valores financeiros;
5. somente então finaliza o registro.

Isso permite que o resultado reflita tanto a interpretação do documento quanto as verificações executadas durante o processamento.

---

# Por que recalcular a confiança em Python?

O modelo pode estar confiante e ainda assim estar errado.

Por esse motivo, a confiança final não depende apenas da autoavaliação do LLM.

O módulo `confidence.py` recalcula a confiança considerando:

* método de extração utilizado;
* resultado das validações;
* consistência dos dados;
* presença de campos obrigatórios;
* justificativas fornecidas.

A decisão de encaminhar um documento para revisão humana é totalmente reproduzível e auditável.

---

# Schema

Cada campo é representado por:

```python
CampoExtraido(
    valor,
    confianca,
    fonte,
    justificativa
)
```

Isso permite auditoria sem necessidade de reabrir o PDF original.

Para cada informação é possível verificar:

* valor extraído;
* confiança atribuída;
* trecho utilizado como fonte;
* justificativa da decisão.

---

# Tipos de evento suportados

* dividendo
* jcp
* bonificação
* grupamento
* desdobramento

Campos são preenchidos apenas quando fazem sentido para o tipo de evento identificado.

---

# Descobertas e premissas sobre o lote fornecido

* Os documentos do lote não são homogêneos.
* Parte dos arquivos contém texto diretamente extraível.
* Alguns documentos são texto puro salvo com extensão `.pdf`.
* O documento `07_telecom_norte_jcp_SCAN.pdf` é um PDF digitalizado e exige OCR.
* O documento 04 possui data de pagamento indefinida ("a definir"), situação tratada como ausência justificada e não como erro de extração.

### Documento 03

O documento 03 merece atenção especial.

O título indica:

```text
Distribuição de Dividendos
```

Porém o corpo do aviso descreve características típicas de Juros sobre Capital Próprio:

* retenção de IRRF;
* cálculo baseado no patrimônio líquido;
* imputação ao dividendo obrigatório.

Por esse motivo o agente foi instruído a classificar pela substância econômica do evento e não apenas pelo título.

Nesses casos a confiança do campo `tipo_evento` é reduzida e o conflito fica explicitamente documentado na justificativa.

---

# O que decidi não fazer

* Não implementei fila persistente para revisão humana.
* Não implementei ensemble de modelos.
* Não implementei pós-processamento especializado para OCR.
* Não implementei interface gráfica para revisão.
* O limiar mínimo de texto extraído utiliza uma regra simples baseada em quantidade de caracteres.

Essas decisões foram tomadas para manter o foco no problema principal do case: extração estruturada, validação e rastreabilidade das informações.

---

# Estrutura de arquivos

```text
case-ai-dev/
├── README.md
├── requirements.txt
├── .env
├── run.py
├── data/golden_records.csv
├── documents/*.pdf
├── src/
│   ├── schema.py
│   ├── ingestion.py
│   ├── tools.py
│   ├── extraction.py
│   ├── confidence.py
│   ├── pipeline.py
│   └── providers/
│       ├── base.py
│       ├── anthropic_provider.py
│       ├── openai_provider.py
│       ├── ollama_provider.py
│       └── factory.py
└── output/
    ├── *.json
    └── exceptions_report.md
```
