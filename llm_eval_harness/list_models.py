from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

from google import genai
client = genai.Client()
for m in client.models.list():
    if "generateContent" in m.supported_actions:
        print(m.name)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
for m in client.models.list():
    print(m.id)
