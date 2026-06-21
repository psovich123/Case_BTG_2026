"""
Orquestração do pipeline ponta a ponta.

Para cada PDF em `documentos/`:
1. Ingestão (texto nativo ou OCR).
2. Extração via agente (Claude + tools de validação).
3. Parse para o schema Pydantic (RegistroEvento).
4. Recálculo determinístico de confiança/roteamento.
5. Grava <documento>.json em output/.
Ao final, gera output/exceptions_report.md consolidando tudo que foi
roteado para revisão humana.
"""
import glob
import json
import os
import traceback

from .ingestion import ingerir_pdf
from .extraction import extrair_registro
from .schema import RegistroEvento, CampoExtraido, ResultadoValidacao, MetodoExtracao
from .confidence import recalcular_confianca_e_roteamento

DOCUMENTOS_DIR = "documents"
OUTPUT_DIR = "output"


def _payload_para_registro(nome_doc: str, metodo: str, payload: dict) -> RegistroEvento:
    campos_payload = payload.get("campos", {})
    campos = {
        nome: CampoExtraido(**dados) if dados else CampoExtraido()
        for nome, dados in campos_payload.items()
    }
    validacoes = [ResultadoValidacao(**v) for v in payload.get("resumo_validacoes", [])]
    return RegistroEvento(
        documento=nome_doc,
        metodo_extracao=MetodoExtracao(metodo),
        validacoes=validacoes,
        **campos,
    )


def processar_documento(caminho_pdf: str) -> RegistroEvento:
    nome_doc = os.path.basename(caminho_pdf)
    ingestao = ingerir_pdf(caminho_pdf)

    print("=" * 80)
    print("FASE - EXTRAÇÃO DE REGISTRO VIA AGENTE")
    print("=" * 80)
    try:
        payload = extrair_registro(nome_doc, ingestao.texto, ingestao.metodo)
        registro = _payload_para_registro(nome_doc, ingestao.metodo, payload)
    except Exception as e:
        # Falha na chamada ao modelo/parse não pode derrubar o lote nem inventar dados:
        # devolve um registro vazio, explicitamente marcado para revisão humana.
        registro = RegistroEvento(
            documento=nome_doc,
            metodo_extracao=MetodoExtracao(ingestao.metodo) if ingestao.metodo in
                [m.value for m in MetodoExtracao] else MetodoExtracao.INDISPONIVEL,
        )
        registro.motivos_revisao = [f"Falha técnica no pipeline de extração: {e}"]
        traceback.print_exc()

    return recalcular_confianca_e_roteamento(registro)


def gerar_relatorio_excecoes(registros: list[RegistroEvento]) -> str:
    linhas = ["# Relatório de Exceções\n"]
    pendentes = [r for r in registros if r.requer_revisao_humana]
    linhas.append(f"Total de documentos processados: {len(registros)}")
    linhas.append(f"Documentos roteados para revisão humana: {len(pendentes)}\n")

    if not pendentes:
        linhas.append("Nenhuma exceção identificada no lote.")
        return "\n".join(linhas)

    for r in pendentes:
        linhas.append(f"## {r.documento}")
        linhas.append(f"- Tipo de evento (extraído): {r.tipo_evento.valor or 'indeterminado'}")
        linhas.append(f"- Confiança geral: {r.confianca_geral}")
        linhas.append("- Motivos para revisão:")
        for m in r.motivos_revisao:
            linhas.append(f"  - {m}")
        linhas.append("")
    return "\n".join(linhas)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pdfs = sorted(glob.glob(os.path.join(DOCUMENTOS_DIR, "*.pdf")))
    
    registros = []
    for caminho in pdfs:
        print(f"Processando {caminho}...")
        registro = processar_documento(caminho)
        registros.append(registro)

        nome_saida = os.path.splitext(os.path.basename(caminho))[0] + ".json"
        with open(os.path.join(OUTPUT_DIR, nome_saida), "w", encoding="utf-8") as f:
            json.dump(registro.model_dump(), f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print("FASE - Geração de relatório de exceções para revisão humana")
    print("=" * 80)

    relatorio = gerar_relatorio_excecoes(registros)
    with open(os.path.join(OUTPUT_DIR, "exceptions_report.md"), "w", encoding="utf-8") as f:
        f.write(relatorio)

    print(f"\nConcluído. {len(registros)} documentos processados.")
    print(f"Saída em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
