"""Run the UnderCover Agent: uv run -m agent [--cap 5] [CLM-1001]"""

import argparse
import sys

from agent.main import call_backend, work_claim
from agent.queue import run_queue


def main(args: list[str]) -> None:
    """Work the claim named on the command line, or run the queue."""
    parser = argparse.ArgumentParser(prog="uv run -m agent")
    parser.add_argument("claim_id", nargs="?", help="work this one claim")
    parser.add_argument("--cap", type=int, help="the most claims the run can take")
    options = parser.parse_args(args)
    if options.claim_id:
        print(work_claim(options.claim_id))
        return
    claims = call_backend("GET", "/api/claims")
    cap = options.cap or sum(claim["status"] == "waiting" for claim in claims)
    if cap == 0:
        print("No claims are waiting.")
        return
    print(run_queue(cap))


if __name__ == "__main__":
    main(sys.argv[1:])
