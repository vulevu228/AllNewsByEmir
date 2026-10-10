"""Entry point for the GitHub Actions workflow (and local runs): one news update.

  python run.py            update data/ and send alert emails (if the email secrets are set)
  python run.py --no-email update data/ only

Local preview afterwards:  python -m http.server -d "data/$web" 8000
"""

import json
import logging
import sys

from news import newswatch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
result = newswatch.run_news(newswatch.store_from_env(), send="--no-email" not in sys.argv)
print(json.dumps(result))
