"""AI Agents: AI that can plan and act.

A tiny, runnable coding agent that demonstrates the agent loop from the slide:

    1. Observe  (see context)
    2. Decide   (plan the next step)
    3. Act      (use tools)
    4. Repeat   (improve)

Task: a temporary workspace contains a buggy `calc.py` and its tests. The agent
inspects files, edits code and runs tests until every test passes.

No dependencies and no API key needed: `plan_next_step` is a rule-based
stand-in for an LLM. Replace its body with a model call to get a real agent;
the loop itself stays exactly the same.

Run:  python agent_loop.py
"""

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_STEPS = 20  # safety net so a confused agent can never loop forever

BUGGY_SOURCE = '''\
def add(a, b):
    return a - b


def multiply(a, b):
    return a + b


def is_even(n):
    return n % 2 == 1
'''

TESTS = '''\
import unittest

from calc import add, is_even, multiply


class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_multiply(self):
        self.assertEqual(multiply(4, 3), 12)

    def test_is_even(self):
        self.assertTrue(is_even(4))
        self.assertFalse(is_even(7))


if __name__ == "__main__":
    unittest.main()
'''

# What the "brain" knows about fixing bugs: function name -> (buggy code, fixed code).
# A real LLM would work this out from the traceback and the source instead.
KNOWN_FIXES = {
    # The `def` line is included so each edit targets exactly one function.
    "add": ("def add(a, b):\n    return a - b", "def add(a, b):\n    return a + b"),
    "multiply": ("def multiply(a, b):\n    return a + b", "def multiply(a, b):\n    return a * b"),
    "is_even": ("def is_even(n):\n    return n % 2 == 1", "def is_even(n):\n    return n % 2 == 0"),
}


# --------------------------------------------------------------------------- #
# Environment: the world the agent can see (observe) and change (execute)
# --------------------------------------------------------------------------- #
class CodeEnvironment:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.files_read: dict[str, str] = {}   # path -> contents the agent has looked at
        self.failing_tests: list[str] = []     # names from the latest test run
        self.tests_passing: bool | None = None  # None = tests never run yet

    # 1. Observe -------------------------------------------------------------
    def observe(self) -> dict:
        return {
            "files": sorted(p.name for p in self.workspace.glob("*.py")),
            "files_read": dict(self.files_read),
            "tests_passing": self.tests_passing,
            "failing_tests": list(self.failing_tests),
        }

    # 3. Act -----------------------------------------------------------------
    def execute(self, action: dict) -> str:
        tool = action["tool"]
        if tool == "run_tests":
            return self._run_tests()
        if tool == "read_file":
            return self._read_file(action["path"])
        if tool == "edit_file":
            return self._edit_file(action["path"], action["old"], action["new"])
        raise ValueError(f"unknown tool: {tool}")

    # Tools ------------------------------------------------------------------
    def _run_tests(self) -> str:
        # -B: no .pyc caching, otherwise same-size edits made within the same
        # second can be masked by a stale bytecode file.
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "-v"],
            cwd=self.workspace, capture_output=True, text=True,
        )
        output = proc.stderr + proc.stdout
        self.failing_tests = re.findall(r"^(?:FAIL|ERROR): (\w+)", output, re.MULTILINE)
        self.tests_passing = proc.returncode == 0
        summary = output.strip().splitlines()[-1] if output.strip() else "no output"
        return f"tests {'PASSED' if self.tests_passing else 'FAILED'} ({summary})"

    def _read_file(self, path: str) -> str:
        text = (self.workspace / path).read_text()
        self.files_read[path] = text
        return f"read {path} ({len(text.splitlines())} lines)"

    def _edit_file(self, path: str, old: str, new: str) -> str:
        target = self.workspace / path
        text = target.read_text()
        if old not in text:
            return f"edit failed: {old!r} not found in {path}"
        target.write_text(text.replace(old, new, 1))
        self.files_read[path] = target.read_text()
        self.tests_passing = None  # code changed: previous test result is stale
        return f"edited {path}: {old!r} -> {new!r}"


@dataclass
class Task:
    goal: str
    environment: CodeEnvironment

    def is_complete(self) -> bool:
        return self.environment.tests_passing is True


# --------------------------------------------------------------------------- #
# 2. Decide: look at the context and choose the next step
# --------------------------------------------------------------------------- #
def plan_next_step(context: dict, task: Task) -> dict:
    # Never ran the tests, or code changed since the last run -> find out where we stand.
    if context["tests_passing"] is None:
        return {"tool": "run_tests", "why": "check the current state of the tests"}

    # Tests are failing but we haven't looked at the code yet -> read it.
    if "calc.py" not in context["files_read"]:
        return {"tool": "read_file", "path": "calc.py",
                "why": f"{len(context['failing_tests'])} test(s) failing, need to see the code"}

    # Fix one failing function per iteration (test_<function> -> <function>).
    source = context["files_read"]["calc.py"]
    for test in context["failing_tests"]:
        func = test.removeprefix("test_")
        if func in KNOWN_FIXES and KNOWN_FIXES[func][0] in source:
            old, new = KNOWN_FIXES[func]
            return {"tool": "edit_file", "path": "calc.py", "old": old, "new": new,
                    "why": f"{test} fails, so fix `{func}`"}

    raise RuntimeError(f"don't know how to fix: {context['failing_tests']}")


# --------------------------------------------------------------------------- #
# The agent loop from the slide
# --------------------------------------------------------------------------- #
def agent_loop(environment: CodeEnvironment, task: Task) -> bool:
    step = 0
    while not task.is_complete():
        step += 1
        if step > MAX_STEPS:
            print(f"\nGave up after {MAX_STEPS} steps.")
            return False
        print(f"\n--- Iteration {step} ---")

        # 1. Observe (see context)
        context = environment.observe()
        print(f"[observe] tests_passing={context['tests_passing']} "
              f"failing={context['failing_tests']}")

        # 2. Decide (plan)
        action = plan_next_step(context, task)
        print(f"[decide]  {action['tool']} - {action['why']}")

        # 3. Act (use tools)
        result = environment.execute(action)
        print(f"[act]     {result}")

        # 4. Repeat (improve): the next observe() sees the effect of this action.

    print(f"\nTask complete in {step} iterations: {task.goal}")
    return True


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_workspace_") as tmp:
        workspace = Path(tmp)
        (workspace / "calc.py").write_text(BUGGY_SOURCE)
        (workspace / "test_calc.py").write_text(TESTS)

        env = CodeEnvironment(workspace)
        task = Task("fix calc.py so all tests pass", env)
        print(f"Goal: {task.goal}")
        ok = agent_loop(env, task)

        if ok:
            print("\nFinal calc.py:\n" + (workspace / "calc.py").read_text())
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
