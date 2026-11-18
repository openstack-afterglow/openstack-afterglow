import argparse
import os

from anthropic import Anthropic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["list", "message", "stream"])
    args = parser.parse_args()
    with Anthropic(
        api_key=os.environ["LUMEN_API_KEY"],
        base_url=os.environ["LUMEN_BASE_URL"].rstrip("/"),
        max_retries=0,
    ) as client:
        if args.operation == "list":
            for model in client.models.list():
                print(model.id)
            return
        options = {
            "model": os.environ["LUMEN_CLAUDE_MODEL"],
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "Explain what an API gateway does in one sentence."}],
        }
        if provider := os.environ.get("LUMEN_CLAUDE_PROVIDER"):
            options["extra_headers"] = {"X-Lumen-Provider": provider}
        if args.operation == "message":
            for block in client.messages.create(**options).content:
                if block.type == "text":
                    print(block.text)
        else:
            with client.messages.stream(**options) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
            print()


if __name__ == "__main__":
    main()
