import json
import os
import subprocess
import sys
import tempfile
import unittest

SCORE = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "score.py")
sys.path.insert(0, os.path.dirname(SCORE))
import score  # noqa: E402

# autoresearch/loop.py's columns, and the root loop.py's (task 261029-172927)
LOOP = ["commit", "metric", "noise", "kept", "idea"]
ROOT_LOOP = ["n", "time", "commit", "metric", "runs", "wall_s", "kept", "idea", "extra"]


class Score(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_dir(self, name, rows, header=LOOP, config={"metric": "cat value.txt"}):
        d = os.path.join(self.root, "runs", name)
        os.makedirs(d)
        with open(os.path.join(d, "results.tsv"), "w") as f:
            f.write("\t".join(header) + "\n")
            for r in rows:
                f.write("\t".join(str(v) for v in r) + "\n")
        if config is not None:
            with open(os.path.join(d, "config.json"), "w") as f:
                json.dump(config, f)
        return d

    def total(self):
        return score.score(self.root)[0]

    def test_no_run_yet_is_zero(self):
        self.assertEqual(self.total(), 0)

    def test_best_kept_reduction_vs_baseline(self):
        self.run_dir("a", [("b", 200, 1, "baseline", "baseline"), ("c1", 150, 1, "yes", "x"),
                           ("c2", 50, 1, "no", "reverted, doesn't count"), ("c3", 120, 1, "yes", "y")])
        self.assertAlmostEqual(self.total(), 40.0)

    def test_baseline_only_is_zero(self):
        self.run_dir("a", [("b", 100, 0, "baseline", "baseline")])
        self.assertEqual(self.total(), 0)

    def test_a_new_run_does_not_lower_the_score(self):
        self.run_dir("old", [("b", 100, 0, "baseline", "baseline"), ("c", 60, 0, "yes", "x")])
        before = self.total()
        self.run_dir("new", [("b", 100, 0, "baseline", "baseline")])
        self.assertAlmostEqual(self.total(), before)
        self.assertAlmostEqual(before, 40.0)

    def test_runs_add_up(self):
        self.run_dir("a", [("b", 100, 0, "baseline", "baseline"), ("c", 60, 0, "yes", "x")])
        self.run_dir("b", [("b", 100, 0, "baseline", "baseline"), ("c", 90, 0, "yes", "x")])
        self.assertAlmostEqual(self.total(), 50.0)

    def test_a_run_without_its_config_is_not_counted(self):
        self.run_dir("a", [("b", 100, 0, "baseline", "baseline"), ("c", 10, 0, "yes", "x")], config=None)
        total, lines = score.score(self.root)
        self.assertEqual(total, 0)
        self.assertIn("not counted", lines[0])

    def test_the_root_loops_log_and_direction(self):
        self.run_dir("w", [(0, "t", "08560925", 375676928, "", 1, "baseline", "baseline", ""),
                           (1, "t", "c20dc3bb", 252090368, "", 1, "yes", "x", ""),
                           (2, "t", "-", 199270400, "", 1, "no", "y", "")],
                     header=ROOT_LOOP, config={"metric": "m", "direction": "min"})
        self.assertAlmostEqual(self.total(), (375676928 - 252090368) / 375676928 * 100)

    def test_higher_is_better_when_the_config_says_so(self):
        self.run_dir("a", [("b", 100, 0, "baseline", "baseline"), ("c", 130, 0, "yes", "x"),
                           ("d", 200, 0, "no", "y")], config={"metric": "m", "direction": "max"})
        self.assertAlmostEqual(self.total(), 30.0)

    def test_the_command_prints_the_number_last(self):
        out = subprocess.run([sys.executable, SCORE, self.root],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip().splitlines()[-1], "0.00")


if __name__ == "__main__":
    unittest.main()
