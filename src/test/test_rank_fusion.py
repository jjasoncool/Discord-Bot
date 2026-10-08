"""名次融合（RRF，`utils/rank_fusion.py`）：關鍵字與向量兩份名單怎麼合成一份。

守的底線：
  - 第 r 名得 weight / (k + r) 分；只看名次，不看各自的原始分數
  - 兩份名單都排前面的，贏過只在一份排第一的
  - 權重調得動某一份名單的影響力；同分照第一次出現的順序，結果穩定

執行：
    cd src && python -m unittest test.test_rank_fusion -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.rank_fusion import fuse_rankings, fused_scores, rrf_score  # noqa: E402


class RankFusionTests(unittest.TestCase):
    def test_score_depends_only_on_rank(self):
        self.assertAlmostEqual(rrf_score(1), 1 / 61)
        self.assertAlmostEqual(rrf_score(2, weight=0.5, k=10), 0.5 / 12)

    def test_item_ranked_well_in_both_lists_wins(self):
        fused = fuse_rankings({"關鍵字": ["a", "b", "c"], "向量": ["b", "d", "a"]})
        # b：第 2＋第 1；a：第 1＋第 3；d、c 只在一份
        self.assertEqual(fused[:2], ["b", "a"])
        self.assertEqual(set(fused), {"a", "b", "c", "d"})

    def test_weights_shift_the_balance(self):
        rankings = {"關鍵字": ["a", "b"], "向量": ["b", "a"]}
        self.assertEqual(fuse_rankings(rankings, weights={"關鍵字": 2.0})[0], "a")
        self.assertEqual(fuse_rankings(rankings, weights={"向量": 2.0})[0], "b")

    def test_ties_keep_first_seen_order(self):
        self.assertEqual(fuse_rankings({"x": ["a"], "y": ["b"]}), ["a", "b"])
        self.assertAlmostEqual(fused_scores({"x": ["a"], "y": ["a"]})["a"], 2 / 61)


if __name__ == "__main__":
    unittest.main()
