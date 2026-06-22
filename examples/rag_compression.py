"""RAG usage: rank retrieved chunks against a query and keep only what matters.

    python examples/rag_compression.py
"""

from tokentrim import compress_rag, count_tokens

CHUNKS = [
    "Bananas are a tropical fruit rich in potassium and grown near the equator.",
    "The payment service tokenizes the card, charges it through the gateway, and "
    "records the transaction id in the ledger. Refunds look up the original record.",
    "Our company picnic is scheduled for the second Friday of July this year.",
    "If a charge fails, the processor retries up to three times before returning "
    "None and emitting a metric named payments.charge.failed.",
    "The cafeteria menu rotates weekly and features a vegetarian option daily.",
]


def main() -> None:
    query = "how does the payment service charge a card and handle failures?"

    before = sum(count_tokens(c) for c in CHUNKS)
    kept = compress_rag(CHUNKS, query, max_chunks=2)
    after = sum(count_tokens(c) for c in kept)

    print(f"Chunks: {len(CHUNKS)} → {len(kept)} kept")
    print(f"Tokens: {before} → {after} ({round((1 - after / before) * 100, 1)}% saved)\n")
    for i, chunk in enumerate(kept, 1):
        print(f"[{i}] {chunk}\n")


if __name__ == "__main__":
    main()
