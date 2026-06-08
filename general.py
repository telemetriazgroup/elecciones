"""Script original: consulta única a la API ONPE por departamento."""

import asyncio
import json

from fetcher import DEPARTAMENTOS, fetch_all_regions


async def main():
    results = await fetch_all_regions()

    with open("onpe_regiones.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("✓ Guardado en onpe_regiones.json")
    print(f"✓ {len(results)} regiones procesadas")

    for r in results:
        if "error" in r:
            print(f"\n{r['region']} ({r['ubigeo']}): ERROR — {r['error']}")
        else:
            print(f"\n{r['region']} ({r['ubigeo']}):")
            print(json.dumps(r, ensure_ascii=False)[:300])


if __name__ == "__main__":
    asyncio.run(main())
