# Code standards

1. Keep it simple, do not overcomplicate.
2. Comments only when necessary.
3. Be concise: a short README and no emojis.
4. IMPORTANT: avoid overly defensive code. Handle exceptions only when necessary.
5. Use uv: ALWAYS `uv run`, NEVER `python3`.
6. TypeScript: strict mode, never `any`.
7. Agents' instructions give the goal, the tools and the rules, with the reason for a rule when it isn't obvious. Don't script a fixed sequence of steps. Steps that never change belong in code, and where the model adds judgment, give it the goal. Give an agent up front what it always needs, and let it look up the rest.
8. Enforce every rule about money or a claim's state in the backend, not only in the prompt, and make it hold when two requests arrive at once. A rule stated only in the instructions can be skipped.
9. One place for each thing: configuration, such as the backend's address, is read in one place, and the agent reaches the backend through one client.
10. Keep harness code (the model, middleware, runs and retries) apart from domain code (claims, decisions and documents).
