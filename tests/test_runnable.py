import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.retrieval import RetrievalConfig
from eval.runnable import missing_requirements

BASELINE = RetrievalConfig(name="0-baseline", chunk_label="line100")
AST      = RetrievalConfig(name="1-ast", chunk_label="ast")
RERANK   = RetrievalConfig(name="3-rerank", chunk_label="ast", use_lexical=True, use_rerank=True)
EXPAND   = RetrievalConfig(name="4-expansion", chunk_label="ast", use_lexical=True,
                           use_rerank=True, use_expansion=True)

ALL_MODULES = {"api.rerank": True, "api.expand": True}
NO_MODULES  = {"api.rerank": False, "api.expand": False}
INDEXED     = {"line100": 307, "ast": 900}


def test_baseline_with_chunks_is_runnable():
    assert missing_requirements(BASELINE, INDEXED, ALL_MODULES, llm_ok=True) == []

def test_config_with_no_chunks_for_its_label_is_not_runnable():
    """The bug this exists to prevent: an unindexed label returns [] from the
    retriever and reports recall=0.000 as if it were a measurement."""
    reasons = missing_requirements(AST, {"line100": 307}, ALL_MODULES, llm_ok=True)
    assert len(reasons) == 1
    assert "ast" in reasons[0] and "no chunks" in reasons[0].lower()

def test_zero_chunks_counts_as_missing():
    reasons = missing_requirements(AST, {"line100": 307, "ast": 0}, ALL_MODULES, llm_ok=True)
    assert reasons and "no chunks" in reasons[0].lower()

def test_rerank_needs_its_module():
    reasons = missing_requirements(RERANK, INDEXED, NO_MODULES, llm_ok=True)
    assert any("api.rerank" in r for r in reasons)

def test_expansion_needs_module_and_llm():
    reasons = missing_requirements(EXPAND, INDEXED, NO_MODULES, llm_ok=False)
    assert any("api.expand" in r for r in reasons)
    assert any("llm" in r.lower() for r in reasons)

def test_expansion_with_module_but_no_llm():
    reasons = missing_requirements(EXPAND, INDEXED, ALL_MODULES, llm_ok=False)
    assert len(reasons) == 1 and "llm" in reasons[0].lower()

def test_baseline_never_needs_llm_or_modules():
    assert missing_requirements(BASELINE, INDEXED, NO_MODULES, llm_ok=False) == []

def test_reports_every_missing_requirement_not_just_the_first():
    """4-expansion also sets use_rerank, so it has four unmet requirements:
    no ast chunks, no api.rerank, no api.expand, no LLM."""
    reasons = missing_requirements(EXPAND, {"line100": 307}, NO_MODULES, llm_ok=False)
    assert len(reasons) == 4
