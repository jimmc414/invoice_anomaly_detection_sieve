"""Initialize the OpenSearch index used for text similarity."""
from __future__ import annotations

import json
import os

from opensearchpy import OpenSearch


def main() -> None:
    host = os.getenv("OS_HOST", "http://localhost:9200")
    client = OpenSearch(hosts=[host])
    index_name = "invoice_text"
    if client.indices.exists(index_name):
        client.indices.delete(index_name)
    template = json.load(open("app/index_templates/invoices_text.json", "r", encoding="utf8"))
    client.indices.create(index=index_name, body=template)
    print("OpenSearch index ready.")


if __name__ == "__main__":  # pragma: no cover
    main()
