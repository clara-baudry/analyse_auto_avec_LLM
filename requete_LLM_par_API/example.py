from dotenv import load_dotenv
import os
from openai import OpenAI
#from langchain_openai import OpenAIEmbeddings

load_dotenv(override=True)

# USERNAME = ""
# EXTRACTION_DATE = ""

# collection_default_name = f"{EXTRACTION_DATE.replace('-','')}"
# COLLECTION_BASENAME = os.getenv(
#     "COLLECTION_BASENAME", f"test_collection_{collection_default_name}"
# )

# EMBEDDING_MODEL = "bge-m3:latest"

# on définit notre client
client = OpenAI(
    base_url = os.getenv("OPENAI_API_URL"),
    api_key = os.getenv("OPENAI_API_KEY")
)

# on définit notre modèle et on lui passe un prompt
completion = client.chat.completions.create(
    model="gemma4-26b-moe",
    messages=[
        {
            "role":"user",
            "content": [
                {"type": "text", "text": "Ecris un sonnet sur l'Insee à la manière de Baudelaire"},
            ],
        },
    ],
)

print(completion.choices[0].message.content)
