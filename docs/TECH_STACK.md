# Tech stack

- `backend/`: FastAPI and SQLite. Every API operation has an `operation_id`, a one-line docstring and no optional inputs. Paying a claim is a separate operation that takes the amount.
- `agent/`: two agents built with LangChain's `create_agent` on OpenRouter, and no other agent framework.
  - The queue agent (`agent/queue.py`) runs the queue. `uv run -m agent --cap 5` starts a run of up to five claims. The agent plans the run as a to-do list and hands each claim to its `work_claim` tool.
  - `work_claim` (`agent/main.py`) works one claim with a fresh claim agent and reports back in one line. `uv run -m agent CLM-1001` runs it on one claim.
  - Both agents reach claims, the documents and their instructions only through the backend's API, at `UNDERCOVER_API` or `http://127.0.0.1:8000`.
  - They use `deepseek/deepseek-v4.1-flash` with low reasoning effort by default, or the model in the environment variable `MODEL_NAME` if set, such as `openrouter/free`.
  - Model calls time out after 60 seconds, and LangChain's `ModelRetryMiddleware` retries them twice.
- `dashboard/`: React, Vite and TypeScript.
- `e2e/`: Playwright tests.
- `data/`: the business data the backend starts from. The agent never sees `data/evals/`, which holds the answer key.

Python 3.12 with uv, all in the root `pyproject.toml`. Node 26. The OpenRouter key is `OPENROUTER_API_KEY` in `.env`.
