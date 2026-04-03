import os
import time
import google.generativeai as genai
from notion_client import Client

# Initialize Clients using Environment Variables
# These will be populated by GitHub Secrets at runtime
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
notion = Client(auth=os.environ["NOTION_TOKEN"])
DATABASE_ID = "3370a91a81e980cdae4ae5e4b4a8f6d9"

# Specify the model. Using 'gemini-1.5-pro' ensures highest reasoning quality
model = genai.GenerativeModel('gemini-1.5-pro')

def process_image(image_path):
    prompt = """
    Extract the core knowledge point from this screenshot.
    Return a JSON object with:
    - title: A concise title.
    - category: One of [LLM, Book, SEO, Productivity, General].
    - content: A structured summary in bullet points.
    - tags: 3 relevant tags.
    """
    
    # Upload and generate
    img = genai.upload_file(path=image_path)
    response = model.generate_content([prompt, img])
    
    # Clean response and parse JSON logic here...
    return response.text

# Logic to loop through images in the /pending folder
# and use notion.pages.create() to add them to the database
