import argparse
import os

from google import genai
from google.genai.types import HttpOptions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["list", "generate", "stream", "embed"])
    args = parser.parse_args()
    options = HttpOptions(base_url=os.environ["LUMEN_BASE_URL"].rstrip("/"), api_version="v1beta")
    prompt = "Explain what an API gateway does in one sentence."
    with genai.Client(api_key=os.environ["LUMEN_API_KEY"], http_options=options, vertexai=False) as client:
        if args.operation == "list":
            for model in client.models.list():
                print(model.name, ", ".join(model.supported_actions or []))
        elif args.operation == "embed":
            result = client.models.embed_content(model=os.environ["LUMEN_GEMINI_EMBED_MODEL"], contents=prompt)
            print("Embedding dimensions:", len(result.embeddings[0].values))
        else:
            config = {}
            if provider := os.environ.get("LUMEN_GEMINI_PROVIDER"):
                config["http_options"] = HttpOptions(headers={"X-Lumen-Provider": provider})
            model = os.environ["LUMEN_GEMINI_MODEL"]
            if args.operation == "generate":
                result = client.models.generate_content(model=model, contents=prompt, config=config)
                print(result.text)
            else:
                for chunk in client.models.generate_content_stream(model=model, contents=prompt, config=config):
                    print(chunk.text or "", end="", flush=True)
                print()


if __name__ == "__main__":
    main()
