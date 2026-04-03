import os
import time
import json
import google.generativeai as genai
from notion_client import Client
from pathlib import Path

# Initialisation
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
notion = Client(auth=os.environ["NOTION_TOKEN"])
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
model = genai.GenerativeModel('gemini-1.5-pro')

def extract_json(text):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    return json.loads(text.strip())

def upload_to_notion(data):
    # Mapping exactly to your 'Tag' property (singular)
    notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties={
            "Name": {"title": [{"text": {"content": data['title']}}]},
            "Category": {"select": {"name": data['category']}},
            "Tag": {"multi_select": [{"name": tag} for tag in data['tags']]}
        },
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": data['content']}}]}
            }
        ]
    )

def main():
    pending_path = Path("pending")
    processed_path = Path("processed")
    processed_path.mkdir(exist_ok=True)

    # Sort files to process in a predictable order
    files = sorted(list(pending_path.glob("*")))
    
    for img_file in files:
        if img_file.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            print(f"Processing: {img_file.name}")
            try:
                uploaded_file = genai.upload_file(path=str(img_file))
                prompt = "Analyze this screenshot. Return ONLY a JSON object with: 'title', 'category' (one of: LLM, Book, SEO, Productivity, General), 'tags' (array of 3), and 'content' (string summary)."
                response = model.generate_content([prompt, uploaded_file])
                
                data = extract_json(response.text)
                upload_to_notion(data)
                
                img_file.rename(processed_path / img_file.name)
                print(f"Success: {img_file.name}")
                
                # 10 second delay to respect Gemini Free Tier RPM (Rate Per Minute)
                time.sleep(10) 
            except Exception as e:
                print(f"Failed to process {img_file.name}: {e}")

if __name__ == "__main__":
    main()
