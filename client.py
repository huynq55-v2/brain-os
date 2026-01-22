from google import genai
from google.genai import types

# Setup Sidebar to enter API Key (for testing convenience)
# api_key = st.sidebar.text_input("Enter Google API Key", type="password")

# read api key from .env file
import os
from dotenv import load_dotenv
load_dotenv()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low")
)

def generate_content(prompt, schema):
    config.response_mime_type = "application/json"
    config.response_json_schema = schema.model_json_schema()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config
    )
    return response.text.strip()