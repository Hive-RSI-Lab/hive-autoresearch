import os
import subprocess
import sys
import tempfile
import unittest

MIN_OF = os.path.join(os.path.dirname(__file__), "..", "metrics", "min_of.py")


class MinOfTest(unittest.TestCase):
    def run_min_of(self, script, n=3):
        with tempfile.TemporaryDirectory() as d:
            counter = os.path.join(d, "n")
            env = dict(os.environ, COUNTER=counter)
            return subprocess.run([sys.executable, MIN_OF, str(n), "--", "sh", "-c", script],
                                  capture_output=True, text=True, env=env)

    def test_prints_the_smallest_number_with_its_runs_fields(self):
        # Runs print 30, 10, 20 in turn.
        script = 'i=$(cat "$COUNTER" 2>/dev/null || echo 0); i=$((i+1)); echo $i > "$COUNTER"; ' \
                 'v=$(echo "30 10 20" | cut -d" " -f$i); echo "run=$i"; echo $v'
        p = self.run_min_of(script)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines(), ["run=2", "min_of=3", "10"])

    def test_a_failing_run_fails_at_once(self):
        script = 'i=$(cat "$COUNTER" 2>/dev/null || echo 0); i=$((i+1)); echo $i > "$COUNTER"; ' \
                 'echo 5; [ $i -lt 2 ]'
        p = self.run_min_of(script)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
