from fastapi import APIRouter

from app.schemas import TermsCorpusCatalog, TermsCorpusQualityResponse, TermsSearchResponse
from app.services.terms_corpus import build_terms_corpus_quality, load_terms_corpus, search_terms_corpus

router = APIRouter(prefix="/v1/terms-corpus", tags=["terms"])


@router.get("", response_model=TermsCorpusCatalog)
def terms_corpus() -> TermsCorpusCatalog:
    return load_terms_corpus()


@router.get("/search", response_model=TermsSearchResponse)
def terms_corpus_search(q: str, top_k: int = 8) -> TermsSearchResponse:
    return search_terms_corpus(query=q, top_k=top_k)


@router.get("/quality", response_model=TermsCorpusQualityResponse)
def terms_corpus_quality() -> TermsCorpusQualityResponse:
    return build_terms_corpus_quality()
