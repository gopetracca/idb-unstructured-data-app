"""Docling as an extraction engine, in-process and offline.

Where the Azure adapter's cost is per page and its risk is the network, this one's cost is
CPU and its risk is a document that takes longer than the caller is willing to wait. The
bounds are therefore layered, cheapest first:

1. **File size**, checked against the bytes already in hand — free, and exact.
2. **Page count**, enforced by Docling as it opens the document, before any model runs.
3. **A cooperative timeout**, which Docling honours at its own checkpoints.

The third is a bound, not a guarantee: a conversion inside a single model inference does
not check for it. Making it a guarantee means running the conversion where it can be
killed — a supervised subprocess — which this adapter deliberately does not do yet. It runs
the conversion on a worker thread so the event loop keeps serving health probes, and says
plainly that the deadline is cooperative. A deployment that needs the hard guarantee needs
the subprocess, and should not read this docstring as claiming one.
"""

import asyncio
import logging
from io import BytesIO
from pathlib import Path

from src.application.ports.document_extractor import DocumentExtractorPort
from src.config.settings import DoclingSettings
from src.core.entities.document_analysis import MarkdownOutput
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.docling.mapper import map_document

logger = logging.getLogger(__name__)

# The content types this adapter accepts, which are not the Azure adapter's: Docling reads
# PowerPoint, Excel, HTML and Markdown that Document Intelligence does not, and the
# capabilities endpoints report whichever engine is configured.
SUPPORTED_FORMATS = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/bmp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/html",
    "text/markdown",
    "text/asciidoc",
    "text/csv",
    "text/plain",
]

# The extension Docling infers the format from, per content type. Docling sniffs the bytes
# too, but the caller already knows what it has, and a name it can trust beats a guess.
_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/asciidoc": ".asciidoc",
    "text/csv": ".csv",
    "text/plain": ".md",
}


class DoclingNotInstalledError(RuntimeError):
    """Raised when Docling is selected but the package is not in the image."""


class DoclingExtractionAdapter(DocumentExtractorPort):
    """Extraction through Docling, satisfying the same contract as every other adapter."""

    def __init__(
        self,
        settings: DoclingSettings,
        converter=None,
    ) -> None:
        """Build the converter once, and fail here rather than on the first document.

        A missing artifacts path is a deployment error, and the place to find out is
        startup — where the readiness probe can still refuse to report ready — not inside a
        queue trigger, where an egress-restricted container would instead hang on a blocked
        download and have its message redelivered.
        """
        self._settings = settings
        self._version = _docling_version()
        self._converter = converter if converter is not None else self._build_converter()

    def get_supported_formats(self) -> list[str]:
        """The content types Docling accepts."""
        return SUPPORTED_FORMATS.copy()

    async def analyze_document(
        self,
        document_content: bytes,
        content_type: str,
        file_id: str,
        file_version: int = 1,
    ) -> MarkdownOutput:
        """Convert a document and project the result onto the canonical model."""
        if not self.is_format_supported(content_type):
            raise UnsupportedFormatError(
                content_type=content_type,
                supported_formats=SUPPORTED_FORMATS,
            )

        size = len(document_content)
        if size > self._settings.max_file_size_bytes:
            raise DocumentProcessingError(
                message=(
                    f"Document is {size} bytes, over the {self._settings.max_file_size_bytes}"
                    " byte limit; conversion was not attempted"
                ),
                file_id=file_id,
                stage="convert",
                details={"reason": "file_size_limit_exceeded", "size_bytes": size},
            )

        logger.info(
            "Docling analyzing document: file_id=%s, content_type=%s, size=%d bytes",
            file_id,
            content_type,
            size,
        )

        # Off the event loop, so a CPU-bound conversion does not stop this worker
        # answering health probes. It does not make the conversion interruptible — see the
        # module docstring.
        result = await asyncio.to_thread(
            self._convert, document_content, content_type, file_id
        )

        status = getattr(result.status, "value", str(result.status))
        if status != "success":
            # Partial success is a failure here on purpose: it means a limit cut the
            # document short, and publishing what was converted would index a document on
            # text that silently stops partway.
            raise DocumentProcessingError(
                message=f"Docling conversion did not complete: status={status}",
                file_id=file_id,
                stage="convert",
                details={
                    "reason": "conversion_incomplete",
                    "status": status,
                    "errors": [str(error) for error in (getattr(result, "errors", None) or [])],
                },
            )

        output = map_document(
            result.document,
            file_id=file_id,
            file_version=file_version,
            api_version=self._version,
            confidence=_confidence(result),
        )
        logger.info(
            "Docling completed: file_id=%s, pages=%d, words=%d, tables=%d",
            file_id,
            output.extraction_metadata.page_count,
            output.extraction_metadata.word_count,
            output.extraction_metadata.table_count,
        )
        return output

    def _convert(self, document_content: bytes, content_type: str, file_id: str):
        """Run the conversion on a worker thread, with the page limit applied by Docling."""
        from docling_core.types.io import DocumentStream

        name = f"{file_id}{_EXTENSIONS.get(content_type.lower(), '')}"
        try:
            return self._converter.convert(
                DocumentStream(name=name, stream=BytesIO(document_content)),
                max_num_pages=self._settings.max_pages,
                max_file_size=self._settings.max_file_size_bytes,
                # Errors come back on the result so the status check above is the single
                # place a failed conversion is turned into a stage failure.
                raises_on_error=False,
            )
        except Exception as error:  # noqa: BLE001 - re-raised as a domain error below
            raise DocumentProcessingError(
                message=f"Docling conversion failed: {error}",
                file_id=file_id,
                stage="convert",
                details={"reason": "conversion_failed"},
            ) from error

    def _build_converter(self):
        """Construct the `DocumentConverter` this adapter reuses for every document."""
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as error:
            raise DoclingNotInstalledError(
                "EXTRACTION_ADAPTER=docling, but this image was built without Docling "
                "support. Install the 'docling' extra, or select another extraction engine."
            ) from error

        artifacts = self._artifacts_path()
        options = PdfPipelineOptions(
            artifacts_path=str(artifacts) if artifacts else None,
            do_ocr=self._settings.do_ocr,
            do_table_structure=self._settings.do_table_structure,
            document_timeout=self._settings.document_timeout_seconds,
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

    def _artifacts_path(self) -> Path | None:
        """The configured model artifacts directory, checked before it is needed.

        Unset means "let Docling find or fetch them", which is right on a workstation. Set
        and absent is a deployment that asked for offline models and does not have them,
        and saying so here is the difference between a startup failure and a queue trigger
        hanging on a download the network will not allow.
        """
        configured = (self._settings.artifacts_path or "").strip()
        if not configured:
            return None
        path = Path(configured)
        if not path.is_dir() or not any(path.iterdir()):
            raise DocumentProcessingError(
                message=(
                    f"DOCLING_ARTIFACTS_PATH={configured!r} is not a directory holding "
                    "Docling model artifacts. Prefetch them with `docling-tools models "
                    "download` and point the setting at the result."
                ),
                stage="convert",
                details={"reason": "missing_model_artifacts"},
            )
        return path


def _docling_version() -> str:
    """The Docling version that produced an output, recorded as its `api_version`."""
    try:
        from importlib.metadata import version

        return version("docling")
    except Exception:  # noqa: BLE001 - a missing version is not worth failing extraction
        return "unknown"


def _confidence(result) -> float:
    """Docling's own document-level confidence, when it reports one.

    Nothing is derived when it does not: a made-up number would be indistinguishable from a
    measured one, and `0.0` already reads as "not reported".
    """
    score = getattr(getattr(result, "confidence", None), "mean_grade", None)
    value = getattr(score, "value", score)
    return float(value) if isinstance(value, (int, float)) else 0.0
