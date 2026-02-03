import sys
import json
import os
import re
import base64
import requests
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
from youtubesearchpython import VideosSearch

# Load environment variables
load_dotenv()

# --- Configuration ---
# Using Qwen2.5-VL-7B-Instruct for high accuracy
MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct" 
HF_TOKEN = os.getenv("HF_TOKEN")

def encode_image_to_base64(image_url):
    """
    Downloads the image locally and converts it to a Base64 data URI.
    This prevents the AI server from getting blocked by Pinterest/Google
    because the request comes from your local machine, not a cloud IP.
    """
    try:
        # User-Agent header makes the request look like a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Convert binary content to base64 string
            encoded_string = base64.b64encode(response.content).decode('utf-8')
            # Create the data URI format required by APIs
            return f"data:image/jpeg;base64,{encoded_string}"
        else:
            return None
    except Exception as e:
        print(f"Error downloading image for encoding: {e}", file=sys.stderr)
        return None

def get_search_query_from_image(image_url):
    """
    Uses Qwen2-VL to analyze the image and generate a precise search query.
    """
    if not HF_TOKEN:
        error_msg = {"error": "HF_TOKEN is not found in the environment variables"}
        print(json.dumps(error_msg), file=sys.stderr)
        return None

    # Step 1: Convert URL to Base64 to bypass blocking
    base64_image_url = encode_image_to_base64(image_url)
    
    if not base64_image_url:
        # Fallback: try sending the raw URL if encoding fails
        print("Warning: Failed to encode image, sending raw URL...", file=sys.stderr)
        base64_image_url = image_url

    client = InferenceClient(token=HF_TOKEN)

    # --- THE IMPROVED PROMPT ---
    # We force the model to break down the image components BEFORE creating the query.
    user_message = (
        "You are an expert DIY analyst. Analyze this image to identify the craft project. "
        "\n\n"
        "Step 1: Identify the **Material/Technique** (e.g., crochet, amigurumi, woodworking, resin). "
        "Step 2: Identify the **Specific Object in Focus**. Be precise (e.g., instead of just 'flower', say 'flower pot' or 'potted plant' or instead of animal, be precide & say which animal if it is recognizable). "
        "Step 3: Identify the **Function/Context** (e.g., keychain, plushie, wall hanging, coaster). "
        "\n\n"
        "Return a JSON object. "
        "\n"
        "- If it is NOT a DIY project (real car, nature, screenshot): {\"valid\": false, \"reason\": \"...\"}\n"
        "- If it IS a DIY project, use this exact structure:\n"
        "{\n"
        "  \"valid\": true,\n"
        "  \"material\": \"...\",\n"
        "  \"specific_object\": \"...\",\n"
        "  \"context\": \"...\",\n"
        "  \"query\": \"[Material] [Specific Object] [Context] tutorial\"\n"
        "}\n"
        "\n"
        "Output ONLY the JSON string & tailor the query peoperly using materials - specific object - context ."
    )

    # Standard OpenAI-compatible message structure for Vision models
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image_url 
                    }
                },
                {
                    "type": "text", 
                    "text": user_message
                }
            ]
        }
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL_ID, 
            messages=messages, 
            max_tokens=200,
            temperature=0.2
        )
        
        output_query = response.choices[0].message.content.strip()
        
        # --- FIX: Markdown Cleanup ---
        # LLMs often wrap code in ```json ... ``` blocks. We must remove them.
        if output_query.startswith("```"):
            output_query = output_query.split("```")[1].strip()
            if output_query.startswith("json"):
                output_query = output_query[4:].strip()
        
        return output_query
        
    except Exception as e:
        print(f"Error calling Qwen2-VL: {e}", file=sys.stderr)
        return None

# ==== helper function to calculate and add scores to the links for better ranking=====

def parse_time_to_years(time_text):
    if not time_text: return 0
    time_text = time_text.lower()
    
    num_match = re.search(r'(\d+)', time_text)
    if not num_match: return 0
    number = int(num_match.group(1))

    if 'year' in time_text: return number
    if 'month' in time_text: return number / 12
    if 'week' in time_text: return number / 52
    if 'day' in time_text: return number / 365
    return 0

def calculate_score(views, time_text):
    """
    UPDATED FORMULA: Score = (ViewsInMillions) / (1.2 ^ YearsOld)
    Example: 
    - 2.4M views, 0 years old -> Score = 2.4
    - 2.4M views, 2 years old -> Score = 2.4 / (1.2^2) = 1.66
    """
    years = parse_time_to_years(time_text)
    if years < 0: years = 0
    
    # Convert raw views to Millions (float)
    views_in_millions = views / 1_000_000
    
    denominator = 1.2 ** years
    
    return round(views_in_millions / denominator, 3)

# --- Helper Functions (Search & Format) ---

def format_view_count(views):
    if not isinstance(views, int): return "N/A"
    try:
        if views >= 1_000_000: return f"{views / 1_000_000:.1f}M"
        elif views >= 1_000: return f"{views // 1000}k"
        else: return str(views)
    except: return "N/A"
    
def get_raw_view_count(view_text):
    if not view_text or 'views' not in view_text.lower(): return 0
    try:
        num_str = ''.join(filter(str.isdigit, view_text))
        return int(num_str) if num_str else 0
    except: return 0

def search_youtube_links(query, limit=10):
    try:
        full_query = f"{query} tutorial"
        
        videos_search = VideosSearch(full_query, limit=20)
        results = videos_search.result()['result']

        tutorials = []
        for video in results:
            view_count_text = video.get('viewCount', {}).get('text', '0 views')
            raw_views = get_raw_view_count(view_count_text)

            time_text = video.get('publishedTime', '')
            score = calculate_score(raw_views,time_text)

            tutorials.append({
                "title": video['title'],
                "url": video['link'],
                "product_name": query, 
                "raw_views": raw_views,
                "score" : score
            })
        
        tutorials = sorted(tutorials, key=lambda x: x['score'], reverse=True)
        
        """final_tutorials = []
        for video in tutorials[:limit]:
            final_tutorials.append({
                "title": video['title'],
                "url": video['url'],
                "product_name": video['product_name'],
                "formatted_views": format_view_count(video['raw_views'])
            })"""
            
        return tutorials

    except Exception as e:
        print(f"Error searching YouTube: {e}", file=sys.stderr)
        return []

# --- Main Execution ---

def main():
    if len(sys.argv) < 2:
        error_message = {"error": "No image URL provided."}
        print(json.dumps(error_message), file=sys.stderr)
        return
    
    image_url = sys.argv[1]

    # Step 1: Get smart query via Base64 bypass
    output_query = get_search_query_from_image(image_url)

    if not output_query:
        error_message = {"error": "Could not generate a search query from the image."}
        print(json.dumps(error_message), file=sys.stderr)
        return
    
    search_query = ""
    tutorials = []
    
    try :
        data = json.loads(output_query)

        valid = data.get("valid")

        if valid is True :
            search_query = data.get("query")
            clean_query = output_query.replace('"', '').replace("Search query:", "").strip()
            tutorials = search_youtube_links(search_query)
            
    except : 
        json.JSONDecodeError("LLM returned bad json that couldn't be parsed")
    

    # Output JSON
    final_output = {
        "product_keyword": search_query, 
        "tutorials": tutorials
    }
    print(json.dumps(final_output))

if __name__ == "__main__":
    main()