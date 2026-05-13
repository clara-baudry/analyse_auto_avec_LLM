Si vous utilisez un .env, y mettre :

OPENAI_API_KEY="sk-..."  
OPENAI_API_URL="https://llm.lab.sspcloud.fr/api/v1"  
QDRANT_SERVER_HOST="..."  
QDRANT_API_KEY="..."  

Autre possibilité : utiliser les secret sur le SSPCloud  

import os  

secrets = os.environ  
secrets['KEY']  