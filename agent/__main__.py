"""Work the claims queue: uv run -m agent [CLAIM_ID ...]"""

import sys

from agent.main import main

main(sys.argv[1:])
