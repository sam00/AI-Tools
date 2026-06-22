"""Basic usage: compress a single block and recover the original.

    python examples/basic_usage.py
"""

from tokentrim import compress_block, count_tokens, retrieve
from tokentrim.samples import JSON_SAMPLE


def main() -> None:
    print(f"Original tokens: {count_tokens(JSON_SAMPLE)}")

    result = compress_block(JSON_SAMPLE)
    print(f"Compressed tokens: {result.compressed_tokens}")
    print(f"Reduction: {round(result.ratio * 100, 1)}%")
    print(f"Reversible: {result.reversible} (ref={result.ref})\n")

    print("--- compressed output (truncated) ---")
    print(result.text[:400])

    if result.ref:
        original = retrieve(result.ref)
        print(f"\nRecovered original matches: {original == JSON_SAMPLE}")


if __name__ == "__main__":
    main()
