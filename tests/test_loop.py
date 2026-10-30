import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "autoresearch"))
import loop  # noqa: E402

# The fake metric prints the number in value.txt; the fake test fails when broken.txt exists.
METRIC = "cat value.txt"
TEST = "test ! -e broken.txt"


class FakeTarget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "target")
        os.makedirs(self.repo)
        self.log = os.path.join(self.tmp.name, "results.tsv")
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", self.repo, *args], check=True)
        self.write("value.txt", "100\n")
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "base"], check=True)
        loop.baseline(self.repo, METRIC, self.log, repeats=2)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(text)

    def read(self, name):
        with open(os.path.join(self.repo, name)) as f:
            return f.read()

    def step(self, idea, **kw):
        return loop.step(self.repo, METRIC, self.log, idea, test=TEST, repeats=2, **kw)

    def test_a_better_change_is_kept(self):
        self.write("value.txt", "80\n")
        kept, _ = self.step("cut it")
        self.assertTrue(kept)
        self.assertEqual(self.read("value.txt"), "80\n")

    def test_a_worse_change_is_reverted(self):
        self.write("value.txt", "120\n")
        kept, _ = self.step("make it worse")
        self.assertFalse(kept)
        self.assertEqual(self.read("value.txt"), "100\n")

    def test_failing_tests_revert_even_a_gain(self):
        self.write("value.txt", "10\n")
        self.write("broken.txt", "")
        kept, why = self.step("cheat")
        self.assertFalse(kept)
        self.assertIn("tests failed", why)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "broken.txt")))
        self.assertEqual(self.read("value.txt"), "100\n")

    def test_a_later_try_is_judged_against_the_best_kept(self):
        self.write("value.txt", "80\n")
        self.assertTrue(self.step("first")[0])
        self.write("value.txt", "90\n")  # better than the baseline, worse than the best
        self.assertFalse(self.step("second")[0])
        self.assertEqual(self.read("value.txt"), "80\n")

    def test_every_try_is_appended_to_the_log(self):
        self.write("value.txt", "80\n")
        self.step("good idea")
        self.write("value.txt", "95\n")
        self.step("bad\tidea\nover lines")
        rows = loop.read_log(self.log)
        self.assertEqual([r["kept"] for r in rows], ["baseline", "yes", "no"])
        self.assertEqual([float(r["metric"]) for r in rows], [100, 80, 95])
        self.assertEqual(rows[2]["idea"], "bad idea over lines")
        with open(self.log) as f:
            self.assertEqual(f.readline().rstrip("\n").split("\t"), loop.HEADER)

    def test_a_log_inside_the_repo_is_refused(self):
        self.write("value.txt", "80\n")
        with self.assertRaises(RuntimeError):
            loop.step(self.repo, METRIC, os.path.join(self.repo, "results.tsv"), "x", test=TEST)

    def test_a_metric_that_fails_is_a_revert(self):
        self.write("value.txt", "not a number\n")
        self.assertFalse(self.step("garbage")[0])
        self.assertEqual(self.read("value.txt"), "100\n")


class Noise(unittest.TestCase):
    def test_spread(self):
        self.assertEqual(loop.noise([10, 12, 11]), 2)
        self.assertEqual(loop.noise([5]), 0)

    def test_a_gain_inside_the_noise_is_not_kept(self):
        self.assertFalse(loop.decide(100, 5, 97, 1)[0])
        self.assertFalse(loop.decide(100, 1, 97, 5)[0])
        self.assertTrue(loop.decide(100, 2, 97, 1)[0])

    def test_direction(self):
        self.assertTrue(loop.decide(100, 0, 110, 0, direction="higher")[0])
        self.assertFalse(loop.decide(100, 0, 110, 0, direction="lower")[0])

    def test_measure_reads_the_last_line(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(loop.measure("echo hi; echo bytes 42", d, repeats=2), [42.0, 42.0])


if __name__ == "__main__":
    unittest.main()
