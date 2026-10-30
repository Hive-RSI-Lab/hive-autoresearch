import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import loop  # noqa: E402  (the root loop.py, the one runs/* ran from)

# The fake metric prints the number in value.txt and fails (the tests failed) when broken.txt exists.
METRIC = "test ! -e broken.txt && cat value.txt"


class FakeTarget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "target")
        self.dir = os.path.join(self.tmp.name, "runs", "fake")
        os.makedirs(self.repo)
        os.makedirs(self.dir)
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", self.repo, *args], check=True)
        self.write("value.txt", "100\n")
        self.write("other.txt", "x\n")
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "base"], check=True)
        self.cfg = self.config()
        self.run_cmd("baseline", runs=2, idea=None)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, **over):
        c = dict(target=self.repo, branch="loop", editable=["value.txt", "new/*"], metric=METRIC,
                 budget_s=30, baseline_runs=2, max_runs=3, max_experiments=20)
        c.update(over)
        path = os.path.join(self.dir, "config.json")
        with open(path, "w") as f:
            json.dump(c, f)
        return loop.load(path)

    def run_cmd(self, cmd, **a):
        with contextlib.redirect_stdout(io.StringIO()):
            getattr(loop, "cmd_" + cmd)(self.cfg, argparse.Namespace(**a))

    def attempt(self, idea):
        self.run_cmd("try", idea=idea)
        return loop.rows(self.cfg)[-1]

    def write(self, name, text):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def read(self, name):
        with open(os.path.join(self.repo, name)) as f:
            return f.read()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args], check=True, text=True,
                              capture_output=True).stdout.strip()

    def test_baseline_makes_the_branch_and_the_first_row(self):
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "loop")
        rows = loop.rows(self.cfg)
        self.assertEqual([(r["n"], r["kept"], r["metric"], r["runs"]) for r in rows], [("0", "baseline", "100", "100,100")])
        self.assertEqual(loop.state(self.cfg)["best"], 100)

    def test_baseline_wants_a_clean_target(self):
        self.write("value.txt", "90\n")
        with self.assertRaises(SystemExit):
            self.run_cmd("baseline", runs=1, idea=None)

    def test_a_better_change_is_kept_as_a_commit(self):
        self.write("value.txt", "80\n")
        before = self.git("rev-parse", "HEAD")
        row = self.attempt("cut it")
        self.assertEqual(row["kept"], "yes")
        self.assertEqual(row["metric"], "80")
        self.assertEqual(self.read("value.txt"), "80\n")
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "cut it")
        self.assertEqual(loop.state(self.cfg)["best"], 80)

    def test_a_worse_change_is_reverted_after_one_run(self):
        self.write("value.txt", "120\n")
        row = self.attempt("make it worse")
        self.assertEqual((row["kept"], row["runs"], row["commit"]), ("no", "120", "-"))
        self.assertEqual(self.read("value.txt"), "100\n")

    def test_a_gain_inside_the_margin_is_reverted(self):
        self.write("value.txt", "99.5\n")  # 0.5% better, min_gain is 1%
        self.assertEqual(self.attempt("too small")["kept"], "no")
        self.assertEqual(self.read("value.txt"), "100\n")

    def test_failing_tests_are_a_crash_and_revert_even_a_gain(self):
        self.write("value.txt", "10\n")
        self.write("new/broken.txt", "")
        self.cfg = self.config(metric="test ! -e new/broken.txt && cat value.txt")
        row = self.attempt("cheat")
        self.assertEqual(row["kept"], "crash")
        self.assertEqual(self.read("value.txt"), "100\n")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "new", "broken.txt")))

    def test_a_failing_prepare_is_a_crash(self):
        self.cfg = self.config(prepare="false")
        self.write("value.txt", "80\n")
        self.assertEqual(self.attempt("won't build")["kept"], "crash")
        self.assertEqual(self.read("value.txt"), "100\n")

    def test_a_metric_over_the_budget_is_a_crash(self):
        self.cfg = self.config(metric="sleep 5; cat value.txt", budget_s=0.2)
        self.write("value.txt", "80\n")
        self.assertEqual(self.attempt("slow")["kept"], "crash")

    def test_a_change_outside_the_editable_files_is_refused(self):
        self.write("value.txt", "80\n")
        self.write("other.txt", "y\n")
        with self.assertRaises(SystemExit):
            self.run_cmd("try", idea="sneaky")
        self.assertEqual(len(loop.rows(self.cfg)), 1)
        self.assertEqual(self.read("other.txt"), "y\n")  # left for the agent to revert

    def test_nothing_changed_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_cmd("try", idea="nothing")

    def test_a_later_try_is_judged_against_the_best_kept(self):
        self.write("value.txt", "80\n")
        self.assertEqual(self.attempt("first")["kept"], "yes")
        self.write("value.txt", "90\n")  # better than the baseline, worse than the best
        self.assertEqual(self.attempt("second")["kept"], "no")
        self.assertEqual(self.read("value.txt"), "80\n")

    def test_every_try_is_logged_with_its_patch(self):
        self.write("value.txt", "80\n")
        self.attempt("good idea")
        self.write("value.txt", "95\n")
        self.attempt("bad\tidea\nover lines")
        rows = loop.rows(self.cfg)
        self.assertEqual([r["kept"] for r in rows], ["baseline", "yes", "no"])
        self.assertEqual([r["n"] for r in rows], ["0", "1", "2"])
        self.assertEqual(rows[2]["idea"], "bad idea over lines")
        with open(loop.tsv(self.cfg)) as f:
            self.assertEqual(f.readline().rstrip("\n").split("\t"), loop.COLUMNS)
        with open(os.path.join(self.dir, "patches", "002.patch")) as f:
            self.assertIn("+95", f.read())

    def test_a_new_untracked_file_is_tried_and_removed_on_revert(self):
        self.write("new/x.txt", "x\n")
        self.write("value.txt", "120\n")
        self.attempt("add a file")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "new", "x.txt")))

    def test_the_cap_stops_the_loop(self):
        self.cfg = self.config(max_experiments=1)
        self.write("value.txt", "120\n")
        self.attempt("one")
        self.write("value.txt", "120\n")
        with self.assertRaises(SystemExit):
            self.run_cmd("try", idea="two")

    def test_key_value_lines_are_logged_as_extras(self):
        self.cfg = self.config(metric="echo syscw=7; cat value.txt")
        self.write("value.txt", "80\n")
        self.assertEqual(self.attempt("extras")["extra"], "syscw=7")

    def test_max_direction(self):
        self.cfg = self.config(direction="max")
        self.write("value.txt", "80\n")
        self.assertEqual(self.attempt("lower is worse now")["kept"], "no")
        self.write("value.txt", "120\n")
        self.assertEqual(self.attempt("higher")["kept"], "yes")

    def test_status_and_plot(self):
        self.write("value.txt", "80\n")
        self.attempt("good")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            loop.cmd_status(self.cfg, None)
        st = json.loads(out.getvalue())
        self.assertEqual((st["best"], st["experiments"], st["kept"]), (80, 1, 1))
        self.run_cmd("plot")
        with open(os.path.join(self.dir, "curve.svg")) as f:
            self.assertIn("<svg", f.read())


class Pure(unittest.TestCase):
    def test_spread(self):
        self.assertAlmostEqual(loop.spread([10, 12, 11]), 2 / 11)
        self.assertEqual(loop.spread([5]), 0)

    def test_margin_is_min_gain_or_three_times_the_noise(self):
        cfg = {"min_gain": 0.01}
        self.assertEqual(loop.margin(cfg, {"noise": 0.001}), 0.01)
        self.assertAlmostEqual(loop.margin(cfg, {"noise": 0.02}), 0.06)

    def test_gain_and_direction(self):
        self.assertAlmostEqual(loop.gain({"direction": "min"}, 80, 100), 0.2)
        self.assertAlmostEqual(loop.gain({"direction": "max"}, 120, 100), 0.2)
        self.assertTrue(loop.better({"direction": "min"}, 80, 100))
        self.assertFalse(loop.better({"direction": "max"}, 80, 100))


class Cli(unittest.TestCase):
    def test_the_script_runs(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        p = subprocess.run([sys.executable, os.path.join(root, "loop.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("baseline", p.stdout)


if __name__ == "__main__":
    unittest.main()
