import sys
import json
import os
import re
import base64
import requests
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
from youtubesearchpython import VideosSearch
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Literal

# Load environment variables
load_dotenv()

#langchain part -------------------------
from langchain_google_genai import ChatGoogleGenerativeAI
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

# MODEL-----------------------------------------------
model = ChatGoogleGenerativeAI(
    model="gemma-4-31b-it",
    temperature=0.0
)

text_model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0.1
)

#langchain part -------------------------

# --- Configuration ---

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
    Uses Gemma-4-31B-it to analyze the image and generate a precise search query.
    """
    if not GEMINI_API_KEY:
        error_msg = {"error": "GEMINI_API_KEY is not found in the environment variables"}
        print(json.dumps(error_msg), file=sys.stderr)
        return None

    # Step 1: Convert URL to Base64 to bypass blocking
    base64_image_url = encode_image_to_base64(image_url)
    
    if not base64_image_url:
        # Fallback: try sending the raw URL if encoding fails
        print("Warning: Failed to encode image, sending raw URL...", file=sys.stderr)
        base64_image_url = image_url

    # PROMPTS -----------------------------------------

    prompt_text = """
        You are an expert Craft and DIY Analyst. Your objective is to meticulously analyze the provided image and deconstruct the handmade project within it. 

        First, determine if the primary subject is a genuine DIY/craft project. If it is a real-life subject (e.g., a real animal, landscape), a mass-produced electronic, a digital screenshot, or AI-generated art masquerading as a physical craft, flag it as invalid and state your reasoning.

        If the image features a valid DIY or craft project, extract the following attributes with high precision:
        1. Material & Technique: Identify the core medium and the crafting method used. Look closely at textures. (Examples: Amigurumi crochet, epoxy resin casting, laser-cut woodworking, wet felting, origami, macrame).
        2. Specific Object: Identify exactly what the item represents. Avoid generic categories. (Examples: "Monstera plant in a terracotta pot" instead of "plant"; "Red panda" instead of "animal"; "Geometric mandala" instead of "pattern").
        3. Form Factor & Context: Determine the functional or physical format of the item. How is it meant to be used or displayed? (Examples: Keychain, stuffed plushie, drink coaster, wall tapestry, desk organizer, wearable pendant).

        Rely strictly on visual evidence. If an element is ambiguous, deduce the most likely answer based on the context of the overall craft.
        Strictly donot give conversational output, follow the format instructions
    """


    # SCHEMAS -----------------------------------------
    class op_schema(BaseModel) :
        
        valid : bool = Field(description=" True if the object in the image is a DIY doable project, else False.")
        object_des : str = Field(description="overall identification & description of the object (for example : 'a crochet camera keychain' or 'an origami rabbit' or 'a valentine card with paper roses' etc... )")
        specific_object : str = Field(description="The precise subject being represented (for example :, Red panda, Monstera plant, camera, any fruit, any card, heart etc.).")
        material : str = Field(description="The core medium and crafting method (for example :, Amigurumi crochet, epoxy resin casting).")
        context : str = Field(description="The physical format or function (for example : keychain, plushie, coaster, wall_hanging, a custom card, greeting card, love card etc, origami model etc.).")

    class final_op_schema(BaseModel) :
        search_querry : str = Field(description="the final single line search query generated by you, using the provided data")



    # MESSAGES -----------------------------------------

    user_message = HumanMessage(
        content=[
            {
                "type": "text", 
                "text": prompt_text,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": base64_image_url
                }
            }
        ]
    )

    structured_model1 = model.with_structured_output(op_schema)
    result1 = structured_model1.invoke([user_message])

    search_text = f"You are an expert search query generator for finding best youtube tutorial of a given DIY object. Given the following precise structural analysis of a DIY project, create an Optimized Search Query.Use the data provided about the object & synthesize these details into a highly targeted, natural-sounding search query designed to find a step-by-step tutorial for this exact item on YouTube. Combine the elements logically into a fluid search phrase. Avoid awkward, purely robotic concatenations (e.g., instead of stitching words blindly, make it read like something a person would type, such as How to make a [Material] [Specific Object] [Form Factor]). End the phrase logically with 'tutorial' and only output a line line, just the optimized search query. here is the data : {result1.material}, {result1.object_des}, {result1.specific_object} & {result1.context}"

    final_msg = HumanMessage(
        content=[
            {
                "type" : "text",
                "text" : search_text
            }
        ]
    )


    try:
        
        structured_text_model = text_model.with_structured_output(final_op_schema)
        final_result = structured_text_model.invoke([final_msg])

        # 1. Convert the Step 1 Pydantic object into a standard Python dictionary
        combined_dict = result1.model_dump()
        
        # 2. Extract the query string from Step 2 using dot notation 
        # and add it to our dictionary
        combined_dict['search_query'] = final_result.search_querry

        # The output is now a single dictionary with all 5 keys: 
        # valid, specific_object, material, context, and search_query
        return combined_dict
        
    except Exception as e:
        print(f"Error calling one of the models: {e}", file=sys.stderr)
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
        valid = output_query["valid"]

        if valid is True :
            search_query = output_query["search_query"]
            tutorials = search_youtube_links(search_query)
            
    except Exception as e: 
        print(f"JSON Parse Error: {e}. Raw AI Output was: {output_query}", file=sys.stderr)
    

    # Output JSON
    final_output = {
        "product_keyword": output_query["object_des"], 
        "tutorials": tutorials
    }
    print(json.dumps(final_output))

if __name__ == "__main__":
    main()