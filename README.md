# AI Agents: AI that can plan and act

A small, runnable Python app that demonstrates the **agent loop** from the slide:

> **Observe → Decide → Act → Repeat**

An AI agent goes beyond answering questions: it can use tools and follow a workflow. This sample is a tiny *coding agent* (the slide's example): it inspects files, edits code, runs tests, and iterates until the tests pass.

## Run it

Requires Python 3.10+ (tested on 3.14). No dependencies and no API key.

```bash
python agent_loop.py
```

Expected result: the agent finishes in 8 iterations and prints the fixed `calc.py`. Exit code is `0` on success, `1` if it gives up.

## The scenario

The app creates a temporary workspace containing:

- `calc.py` with three deliberate bugs (`add` subtracts, `multiply` adds, `is_even` is inverted).
- `test_calc.py` with one unit test per function.

The **task** is: *fix `calc.py` so all tests pass.* The agent does not know the answer up front. It has to discover what is failing and fix it step by step.

## The loop (the slide's snippet)

The heart of the app is `agent_loop`, a direct implementation of the slide's Python snippet:

```python
def agent_loop(environment, task):
    while not task.is_complete():
        # 1. Observe (see context)
        context = environment.observe()

        # 2. Decide (plan)
        action = plan_next_step(context, task)

        # 3. Act (use tools)
        environment.execute(action)

        # 4. Repeat (improve)
```

| Step | Slide label | In this code | What happens |
|------|-------------|--------------|--------------|
| 1 | Observe (see context) | `environment.observe()` | Returns a snapshot: files present, files already read, whether tests pass, which tests fail. |
| 2 | Decide (plan) | `plan_next_step(context, task)` | Looks at the snapshot and picks **one** next action. |
| 3 | Act (use tools) | `environment.execute(action)` | Runs the chosen tool and returns a result message. |
| 4 | Repeat (improve) | the `while` loop | The next `observe()` sees the effect of the last action, so the agent improves each pass. |

The loop ends when `task.is_complete()` is true, i.e. the tests pass. A `MAX_STEPS = 20` guard stops a confused agent from looping forever.

## Code walkthrough

### `CodeEnvironment`: the world the agent lives in

Holds the workspace and the agent's knowledge of it:

```python
self.files_read      # path -> contents the agent has looked at
self.failing_tests   # test names from the latest run
self.tests_passing   # None = never run / stale, True / False = last result
```

- **`observe()`** builds the context dictionary the agent reasons about.
- **`execute(action)`** dispatches to one of the agent's three **tools**:

| Tool | Purpose |
|------|---------|
| `run_tests` | Runs `python -B -m unittest -v` in the workspace, parses the names of failing tests, and sets `tests_passing`. |
| `read_file` | Reads a file and stores its contents in `files_read` so the agent can "see" it. |
| `edit_file` | Replaces `old` text with `new` text in a file. Resets `tests_passing` to `None`, because the earlier test result is now stale and the agent must re-run the tests. |

### `Task`

```python
@dataclass
class Task:
    goal: str
    environment: CodeEnvironment

    def is_complete(self) -> bool:
        return self.environment.tests_passing is True
```

The goal in words plus a check for "are we done?". Done means the last test run passed.

### `plan_next_step`: the "Decide" step

This is the agent's brain. It is three simple rules, applied in order:

```python
# 1. Unknown state (never ran tests, or code changed since) -> run the tests
if context["tests_passing"] is None:
    return {"tool": "run_tests", ...}

# 2. Tests fail but the code hasn't been read -> read it
if "calc.py" not in context["files_read"]:
    return {"tool": "read_file", "path": "calc.py", ...}

# 3. Fix one failing function (test_<function> -> <function>)
for test in context["failing_tests"]:
    ...
    return {"tool": "edit_file", "old": old, "new": new, ...}
```

Each returned action carries a `why` string, which is printed so you can follow the agent's reasoning.

`KNOWN_FIXES` maps each function name to its buggy and fixed code. Each entry includes the `def` line so an edit targets exactly one function (`add` and `multiply` share the text `return a + b` once `add` is fixed).

> **Important:** `plan_next_step` is a rule-based stand-in for an LLM. In a real agent you would replace its body with a model call that receives `context` and the tool list and returns the next action. **The loop itself does not change.**

## Example output

Each iteration prints the three phases, so you can see the loop working:

```text
--- Iteration 1 ---
[observe] tests_passing=None failing=[]
[decide]  run_tests - check the current state of the tests
[act]     tests FAILED (FAILED (failures=3))

--- Iteration 2 ---
[observe] tests_passing=False failing=['test_add', 'test_is_even', 'test_multiply']
[decide]  read_file - 3 test(s) failing, need to see the code
[act]     read calc.py (10 lines)

--- Iteration 3 ---
[observe] tests_passing=False failing=['test_add', 'test_is_even', 'test_multiply']
[decide]  edit_file - test_add fails, so fix `add`
[act]     edited calc.py: 'def add(a, b):\n    return a - b' -> 'def add(a, b):\n    return a + b'
...
--- Iteration 8 ---
[observe] tests_passing=None failing=['test_multiply']
[decide]  run_tests - check the current state of the tests
[act]     tests PASSED (OK)

Task complete in 8 iterations: fix calc.py so all tests pass
```

The 8 iterations break down as: run tests, read the file, then (fix + re-run) three times.

## Design notes

- **Observe before acting.** The agent never edits code it has not read, and never trusts a stale test result.
- **One action per iteration.** Small steps make each decision easy to follow and each result easy to verify.
- **Feedback drives progress.** The failing-test count drops 3 → 2 → 1 → 0, and that is the "Repeat (improve)" part of the loop.
- **Tests run with `python -B`.** This disables `.pyc` caching. Without it, same-size edits made within the same second (`-` → `+`) can be masked by stale bytecode and the tests would keep reporting old failures.
- **The workspace is temporary.** It is deleted when the program exits, so nothing in this folder is modified by running the sample.

## Ideas to extend it

- Replace `plan_next_step` with a call to an LLM (for example the Claude API with tool use) and let the model choose among `run_tests`, `read_file` and `edit_file`.
- Add more tools (list files, search, run a shell command).
- Add a new bug and watch the agent fail with `don't know how to fix`, then extend `KNOWN_FIXES` or the planner.
