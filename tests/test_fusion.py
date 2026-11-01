from src.fusion import reciprocal_rank_fusion
from src.models import ChunkingStrategy, DocumentChunk


def _chunk(id_):
    return DocumentChunk(id=id_, text=f"text {id_}", source_file="a.md", title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)


def test_chunk_in_both_lists_ranks_above_single_list_hits():
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    dense = [(a, 0.9), (b, 0.8)]
    sparse = [(a, 5.0), (c, 3.0)]

    fused = reciprocal_rank_fusion(dense, sparse)
    assert fused[0].chunk.id == "a"  # appears in both, rank 1 in both
    assert {f.chunk.id for f in fused} == {"a", "b", "c"}


def test_dense_weight_influences_ranking():
    a, b = _chunk("a"), _chunk("b")
    dense = [(a, 0.9)]  # a is dense rank 1, absent from sparse
    sparse = [(b, 5.0)]  # b is sparse rank 1, absent from dense

    dense_heavy = reciprocal_rank_fusion(dense, sparse, dense_weight=0.9, sparse_weight=0.1)
    assert dense_heavy[0].chunk.id == "a"

    sparse_heavy = reciprocal_rank_fusion(dense, sparse, dense_weight=0.1, sparse_weight=0.9)
    assert sparse_heavy[0].chunk.id == "b"


def test_empty_inputs_return_empty():
    assert reciprocal_rank_fusion([], []) == []


def test_dense_only_when_sparse_empty():
    a = _chunk("a")
    fused = reciprocal_rank_fusion([(a, 0.5)], [])
    assert len(fused) == 1
    assert fused[0].sparse_rank is None
    assert fused[0].dense_rank == 1


def test_scores_are_recorded_on_candidates():
    a = _chunk("a")
    fused = reciprocal_rank_fusion([(a, 0.77)], [(a, 12.3)])
    assert fused[0].dense_score == 0.77
    assert fused[0].sparse_score == 12.3
    assert fused[0].rrf_score > 0
