from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv(override=True)

client = OpenAI(
    base_url = os.getenv("OPENAI_API_URL"),
    api_key = os.getenv("OPENAI_API_KEY")
)

models = client.models.list()
model_list = list(models)  # convertit en liste Python standard

# 1. Combien de modèles ?
print(len(model_list)) # il y a 3 modèles

# 2. Juste les IDs (ce qui t'intéresse pour model="...")
for m in model_list:
    print(m.id)

# donc, modèles disponibles
# gemma4-26b-moe
# qwen3-6-35b-moe
# qwen3-embedding-8b

# 3. Inspecter un modèle en détail
m = model_list[0]
print(m.id)
print(m.info)          # dict complet
print(m.info['meta']['capabilities'])  # ce qu'il sait faire

# 4. Filtrer les modèles actifs avec vision
for m in model_list:
    caps = m.info.get('meta', {}).get('capabilities', {})
    if caps.get('vision') and m.info.get('is_active'):
        print(m.id)