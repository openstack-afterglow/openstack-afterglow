import argparse
import base64
import os
from pathlib import Path

from openai import OpenAI


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["list", "chat", "responses", "stream", "embed", "image", "providers"])
    args = parser.parse_args()
    root = os.environ["LUMEN_BASE_URL"].rstrip("/")
    prompt = "Explain what an API gateway does in one sentence."
    messages = [{"role": "user", "content": prompt}]
    with OpenAI(api_key=os.environ["LUMEN_API_KEY"], base_url=f"{root}/v1", max_retries=0) as client:
        if args.operation == "list":
            for model in client.models.list():
                print(model.id)
        elif args.operation == "chat":
            result = client.chat.completions.create(model=os.environ["LUMEN_OPENAI_MODEL"], messages=messages)
            print(result.choices[0].message.content)
        elif args.operation == "responses":
            result = client.responses.create(model=os.environ["LUMEN_OPENAI_MODEL"], input=prompt)
            print(result.output_text)
        elif args.operation == "stream":
            with client.chat.completions.create(model=os.environ["LUMEN_OPENAI_MODEL"], messages=messages, stream=True) as stream:
                for chunk in stream:
                    if chunk.choices:
                        print(chunk.choices[0].delta.content or "", end="", flush=True)
            print()
        elif args.operation == "embed":
            result = client.embeddings.create(model=os.environ["LUMEN_OPENAI_EMBED_MODEL"], input=prompt)
            print("Embedding dimensions:", len(result.data[0].embedding))
        elif args.operation == "image":
            result = client.images.generate(model=os.environ["LUMEN_IMAGE_MODEL"], prompt="A paper boat on still water", n=1)
            image = result.data[0].b64_json
            if not image:
                raise RuntimeError("Lumen did not return an image")
            with Path("lumen-python-image.png").open("xb") as output:
                output.write(base64.b64decode(image))
            print("Saved lumen-python-image.png")
        elif args.operation == "providers":
            for family in ("CLAUDE", "GEMINI"):
                provider = os.environ[f"LUMEN_{family}_PROVIDER"]
                result = client.chat.completions.create(
                    model=os.environ[f"LUMEN_{family}_MODEL"],
                    extra_headers={"X-Lumen-Provider": provider},
                    messages=messages,
                )
                print(f"{provider}: {result.choices[0].message.content}")


if __name__ == "__main__":
    main()
