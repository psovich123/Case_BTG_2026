"""
Camada de ingestão de PDFs.

Estratégia:
1. Tenta extrair texto nativo via pdfplumber (rápido, confiável).
2. Se o resultado vier vazio/curto demais (PDF escaneado, ou arquivo
   corrompido/vazio como o caso 07 do lote), tenta OCR via
   pdf2image + pytesseract.
3. Se nem isso funcionar, devolve texto vazio e método "indisponivel" -
   o pipeline deve tratar isso como confiança mínima e roteamento
   humano obrigatório, NUNCA inventar conteúdo.

Limiar de "texto curto demais" é deliberadamente simples (nº de
caracteres) porque o objetivo aqui é decidir entre dois caminhos
determinísticos, não fazer NLP.
"""
import pdfplumber
from dataclasses import dataclass

MIN_CHARS_TEXTO_NATIVO = 80  # abaixo disso, tratamos como "sem texto nativo confiável"


@dataclass
class ResultadoIngestao:
    texto: str
    metodo: str  # "texto_nativo" | "ocr" | "indisponivel"
    paginas: int


def extrair_texto_nativo(caminho_pdf: str) -> str:
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            partes = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(partes).strip()
    except Exception:
        return ""


def extrair_como_texto_puro(caminho_pdf: str) -> str:
    """Fallback para arquivos com extensão .pdf que na verdade não são PDFs binários válidos
    (ex.: texto puro salvo com a extensão errada). Isso é um problema de qualidade de dados de
    origem, não de OCR - por isso é tratado separadamente e sinalizado no metodo_extracao."""
    try:
        with open(caminho_pdf, "rb") as f:
            raw = f.read()
        if raw.startswith(b"%PDF"):
            return ""  # é um PDF binário de fato; não é o caso deste fallback
        return raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def extrair_via_ocr(caminho_pdf: str) -> str:
    import fitz
    import pytesseract
    from PIL import Image
    import io
    import os
    
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
    # ajuste para o caminho do tesseract no seu sistema
    try:
        pdf = fitz.open(caminho_pdf)

        textos = []

        for pagina in pdf:
            pix = pagina.get_pixmap(
                matrix=fitz.Matrix(2, 2),
                alpha=False
            )

            img = Image.open(io.BytesIO(pix.tobytes("png"))
            )

            texto = pytesseract.image_to_string(
                img,
                lang="por"
            )

            textos.append(texto)

        return "\n".join(textos)

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return ""


def ingerir_pdf(caminho_pdf: str) -> ResultadoIngestao:
    texto_nativo = extrair_texto_nativo(caminho_pdf)
    if len(texto_nativo) >= MIN_CHARS_TEXTO_NATIVO:
        return ResultadoIngestao(texto=texto_nativo, metodo="texto_nativo", paginas=1)

    texto_puro = extrair_como_texto_puro(caminho_pdf)
    if len(texto_puro) >= MIN_CHARS_TEXTO_NATIVO:
        return ResultadoIngestao(texto=texto_puro, metodo="texto_plano", paginas=1)

    texto_ocr = extrair_via_ocr(caminho_pdf)
    if len(texto_ocr) >= MIN_CHARS_TEXTO_NATIVO:
        return ResultadoIngestao(texto=texto_ocr, metodo="ocr", paginas=1)

    # Nem texto nativo, nem texto puro, nem OCR produziram conteúdo utilizável
    # (cobre o caso de arquivo vazio/corrompido, como o doc 07 do lote)
    return ResultadoIngestao(texto=texto_ocr or texto_puro or texto_nativo, metodo="indisponivel", paginas=0)
