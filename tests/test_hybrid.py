import unittest

from labs.hybrid.retrieval import Document, Hit, bm25_rank, rerank, rrf_fuse, vector_rank


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.docs = [
            Document("exact", "E104 connection timeout while opening a socket"),
            Document("policy", "Refund reimbursement is available within seven days"),
            Document("other", "Delivery shipping options are listed here"),
        ]

    def test_bm25_finds_exact_code(self):
        self.assertEqual(bm25_rank(self.docs, "E104")[0].document.id, "exact")

    def test_vector_uses_supplied_embeddings(self):
        hits = vector_rank(self.docs, [[1, 0], [0, 1], [0, 1]], [1, 0])
        self.assertEqual(hits[0].document.id, "exact")

    def test_rrf_deduplicates_and_keeps_sources(self):
        fused = rrf_fuse(bm25_rank(self.docs, "refund"), [Hit(self.docs[1], 0.9, ("vector",))])
        self.assertEqual(fused[0].document.id, "policy")
        self.assertEqual(set(fused[0].sources), {"bm25", "vector"})

    def test_rerank_is_bounded_to_candidates(self):
        candidates = bm25_rank(self.docs, "shipping")
        self.assertEqual({hit.document.id for hit in rerank("shipping", candidates, scorer=lambda q, texts: [1] * len(texts))}, {"other"})

    def test_reranker_failures_propagate(self):
        with self.assertRaises(ValueError):
            rerank("E104", bm25_rank(self.docs, "E104"), scorer=lambda q, t: [])

    def test_vector_invalid_dimension(self):
        with self.assertRaises(ValueError):
            vector_rank(self.docs, [[1], [1], [1]], [1, 2])

    def test_rrf_hand_calculation(self):
        a, b = self.docs[:2]
        result = rrf_fuse([Hit(a, 10), Hit(b, 9)], [Hit(b, .8)], k=1)
        self.assertEqual(result[0].document.id, b.id)
        self.assertAlmostEqual(result[0].score, 1/3 + 1/2)

    def test_duplicate_id_in_one_ranking_rejected(self):
        with self.assertRaises(ValueError):
            rrf_fuse([Hit(self.docs[0], 1), Hit(self.docs[0], 2)])

    def test_invalid_rrf_parameter(self):
        with self.assertRaises(ValueError):
            rrf_fuse([], k=0)


if __name__ == "__main__":
    unittest.main()
