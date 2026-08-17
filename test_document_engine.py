import tempfile
import unittest
from pathlib import Path

from document_engine.config import EngineConfig, LegalMetadata
from document_engine.legal import LegalParser, article_label, inventory
from document_engine.models import BlockRole, Polygon, ProviderDocument, ReconciledBlock, ReviewState, TextBlock
from document_engine.pipeline import DocumentEngine
from document_engine.providers import DocumentProvider
from document_engine.reconcile import remove_repeated_marginals
from ingestion_admin import _valider_chunk


def rb(page, text, role=BlockRole.PARAGRAPH, top=.2, bottom=.3):
    return ReconciledBlock(page, text, role, .99, ReviewState.CONFIRMED,
                           Polygon(((0, top), (1, top), (1, bottom), (0, bottom))))


class StaticProvider(DocumentProvider):
    def __init__(self, name, blocks, pages=2): self.name, self.blocks, self.pages = name, blocks, pages
    def analyze(self, pdf): return ProviderDocument(self.name, self.pages, self.blocks)


class LegalParserTests(unittest.TestCase):
    def test_compound_article_labels(self):
        self.assertEqual(article_label("Article 27.1.- Texte"), "Article 27.1")
        self.assertEqual(article_label("Article 1er bis.- Texte"), "Article 1er bis")
        self.assertEqual(article_label("Article 174 ter : Texte"), "Article 174 ter")

    def test_heading_belongs_to_next_article(self):
        units = LegalParser().parse([
            rb(1, "TITRE I", BlockRole.SECTION_HEADING), rb(1, "Article 1.- Premier."),
            rb(1, "CHAPITRE II", BlockRole.SECTION_HEADING), rb(1, "Article 2.- Deuxième."),
        ])
        self.assertEqual(units[0].label, "Article 1")
        self.assertNotIn("CHAPITRE II", units[0].content)
        self.assertIn("CHAPITRE II", units[1].content)
        self.assertEqual(units[1].path, "TITRE I > CHAPITRE II")

    def test_inventory_detects_gap_and_duplicate(self):
        units = LegalParser().parse([rb(1, "TITRE I", BlockRole.SECTION_HEADING), rb(1, "Article 1.- A"),
                                     rb(1, "Article 3.- C"), rb(1, "Article 3.- C bis")])
        result = inventory(units)
        self.assertEqual(result["numeric_missing"], [2])
        self.assertEqual(result["duplicates"], ["Article 3"])


class HeaderTests(unittest.TestCase):
    def test_repeated_header_removed_but_legal_reference_kept(self):
        blocks = []
        for page in range(1, 5):
            blocks.extend([rb(page, f"Spécial No 11 - LE MONITEUR - {page}", BlockRole.PAGE_HEADER, .01, .04),
                           rb(page, "Le texte publié au journal Le Moniteur reste applicable.", top=.3, bottom=.4)])
        kept, removed = remove_repeated_marginals(blocks, 4, EngineConfig())
        self.assertEqual(len(removed), 4)
        self.assertEqual(len(kept), 4)


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_review_queue_and_metadata(self):
        def block(provider, page, text, role, ident, confidence=.99, top=.2):
            return TextBlock(page, text, role, confidence, Polygon(((0, top), (1, top), (1, top+.05), (0, top+.05))), provider, ident)
        primary = StaticProvider("google", [
            block("google", 1, "TITRE I", BlockRole.SECTION_HEADING, "g1"),
            block("google", 1, "Article 1.- Texte exact.", BlockRole.PARAGRAPH, "g2", top=.3),
            block("google", 2, "Article 2.- Régime applicable.", BlockRole.PARAGRAPH, "g3", top=.3),
        ])
        verifier = StaticProvider("azure", [
            block("azure", 1, "TITRE I", BlockRole.SECTION_HEADING, "a1"),
            block("azure", 1, "Article 1.- Texte exact.", BlockRole.PARAGRAPH, "a2", top=.3),
            block("azure", 2, "Article 2.- Réoime applicable.", BlockRole.PARAGRAPH, "a3", top=.3),
        ])
        metadata = LegalMetadata("Test", "Test", "decret", "2026-01-01", "2026-01-02",
                                 moniteur_publication="Le Moniteur, 181e année, Spécial no 1, 2 janvier 2026",
                                 type_thematique=("droit_administratif",))
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "test.pdf"; pdf.write_bytes(b"fixture")
            result = DocumentEngine(primary, verifier).process(pdf, metadata)
        self.assertEqual(result.report["status"], "review_required")
        self.assertTrue(result.review_queue)
        self.assertEqual(result.chunks[0]["metadata"]["chemin_hierarchique"], "TITRE I")
        self.assertEqual(result.chunks[0]["metadata"]["moniteur_publication"], "Le Moniteur, 181e année, Spécial no 1, 2 janvier 2026")
        self.assertEqual(result.chunks[0]["metadata"]["date_publication"], "2026-01-02")
        self.assertFalse([error for i, chunk in enumerate(result.chunks) for error in _valider_chunk(chunk, i)[0]])


if __name__ == "__main__": unittest.main()
