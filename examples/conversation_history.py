"""Conversation usage: compress chat history before sending to the LLM.

    python examples/conversation_history.py
"""

from tokentrim import compress, count_tokens
from tokentrim.samples import LOG_SAMPLE


def main() -> None:
    messages = [
        {"role": "system", "content": "You are a senior SRE assistant."},
        {"role": "user", "content": "Why did the worker crash? Here are the logs."},
        {"role": "tool", "content": LOG_SAMPLE},
        {"role": "assistant", "content": "Analyzing the log stream now."},
        {"role": "user", "content": "Focus on the fatal error."},
    ]

    before = sum(count_tokens(_text(m)) for m in messages)
    compressed = compress(messages, keep_last=2)
    after = sum(count_tokens(_text(m)) for m in compressed)

    print(f"Conversation tokens: {before} → {after} "
          f"({round((1 - after / before) * 100, 1)}% saved)\n")
    print("Tool message after compression:\n")
    print(compressed[2]["content"][:600])


def _text(message: dict) -> str:
    content = message.get("content")
    return content if isinstance(content, str) else ""


if __name__ == "__main__":
    main()
