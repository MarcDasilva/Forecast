from __future__ import annotations

import asyncio
import json

from forecast.tasks.specialists import run_all_specialist_agents


async def main() -> None:
    results = await run_all_specialist_agents()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
