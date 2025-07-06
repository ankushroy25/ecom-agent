from flask import Flask, request, jsonify, session
import requests
import os
from groq import Groq
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from uuid import uuid4

load_dotenv()

app = Flask(__name__)


# Environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERVER_URL = os.getenv("SERVER_URL")

# PostgreSQL configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

client = Groq(api_key=GROQ_API_KEY)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_secret_key")


# Global in-memory session storage
SESSION_CONTEXT = {}


def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None


def fetch_available_products():
    """Fetch available product names from database"""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT name FROM products.productitem GROUP BY name")
            result = cursor.fetchall()
            return [row['name'] for row in result]
    except psycopg2.Error as e:
        print(f"Error fetching products: {e}")
        return []
    finally:
        conn.close()


def fetch_available_food_items():
    """Fetch available food item names from database"""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT name FROM food.menu_items GROUP BY name")
            result = cursor.fetchall()
            return [row['name'] for row in result]
    except psycopg2.Error as e:
        print(f"Error fetching food items: {e}")
        return []
    finally:
        conn.close()


def get_suggested_items_and_products(user_query, available_food_items, available_products):
    """Get AI suggestions limited to available items in database"""

    # Create a more focused prompt with examples
    system_prompt = """
    You are a smart assistant for an e-commerce platform. Given a user's request for planning an event or outing, suggest both food items and products needed for that event.

    You must ONLY suggest items from the provided available lists. Choose items that are most suitable for the requested event.

    Return ONLY a valid JSON object in this exact format and do not include any additional text or explanations:
    {
        "food_items": ["item1", "item2", "item3"],
        "products": ["product1", "product2", "product3"]
    }

    Rules:
    - Select an ample amount of food items and products maximum 8 each
    - Only use items from the provided lists
    - No additional text or explanations
    - Must be valid JSON format
    """

    # Create user message with available items
    user_message = f"""
    User Request: {user_query}

    Available Food Items: {available_food_items[:50]}  # Limit to first 50 items to avoid token limits
    Available Products: {available_products[:50]}  # Limit to first 50 items to avoid token limits

    Select appropriate items for this request and return only the JSON object.
    """

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_completion_tokens=500,
            top_p=0.9,
            stream=False,
            stop=None,
        )

        suggested_data = completion.choices[0].message.content.strip()
        print(f"Raw AI response: {suggested_data}")

        # Clean up the response - remove any markdown formatting
        if suggested_data.startswith('```json'):
            suggested_data = suggested_data.replace(
                '```json', '').replace('```', '').strip()
        elif suggested_data.startswith('```'):
            suggested_data = suggested_data.replace('```', '').strip()

        # Try to parse JSON
        try:
            result = json.loads(suggested_data)
            print(f"Parsed suggestions: {result}")
            return result
        except json.JSONDecodeError:
            print("JSON parsing failed, trying to extract JSON from response")
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{.*\}', suggested_data, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    print(f"Extracted suggestions: {result}")
                    return result
                except json.JSONDecodeError:
                    pass

        # If all parsing fails, create a fallback response
        print("All parsing failed, creating fallback suggestions")
        return create_fallback_suggestions(user_query, available_food_items, available_products)

    except Exception as e:
        print(f"Error in AI completion: {e}")
        return create_fallback_suggestions(user_query, available_food_items, available_products)


def create_fallback_suggestions(user_query, available_food_items, available_products):
    """Create fallback suggestions when AI fails"""
    import random

    query_lower = user_query.lower()

    # Basic event type detection
    suggested_food = []
    suggested_products = []

    # Food suggestions based on event type
    if "birthday" in query_lower or "party" in query_lower:
        food_keywords = ["cake", "burger", "pizza",
                         "brownie", "cupcake", "muffin"]
        product_keywords = ["lights", "poppers", "curtain", "towels"]
    elif "picnic" in query_lower or "outdoor" in query_lower:
        food_keywords = ["sandwich", "chips", "juice", "water", "snacks"]
        product_keywords = ["towels", "wipes", "storage", "bag"]
    elif "dinner" in query_lower or "meal" in query_lower:
        food_keywords = ["biryani", "curry", "naan", "rice", "dal"]
        product_keywords = ["plates", "storage", "cleaner"]
    else:
        # Default suggestions
        food_keywords = ["burger", "pizza", "coffee", "tea", "snacks"]
        product_keywords = ["storage", "cleaner", "towels"]

    # Find matching food items
    for keyword in food_keywords:
        matches = [item for item in available_food_items if keyword.lower()
                   in item.lower()]
        if matches:
            suggested_food.extend(matches[:2])

    # Find matching products
    for keyword in product_keywords:
        matches = [item for item in available_products if keyword.lower()
                   in item.lower()]
        if matches:
            suggested_products.extend(matches[:2])

    # If no matches found, use random selection
    if not suggested_food and available_food_items:
        suggested_food = random.sample(
            available_food_items, min(3, len(available_food_items)))

    if not suggested_products and available_products:
        suggested_products = random.sample(
            available_products, min(3, len(available_products)))

    # Remove duplicates and limit
    suggested_food = list(dict.fromkeys(suggested_food))[:5]
    suggested_products = list(dict.fromkeys(suggested_products))[:5]

    return {
        "food_items": suggested_food,
        "products": suggested_products
    }


def fetch_food_search_results(item_list):
    """Fetch top 3 rated food items per name directly from PostgreSQL"""
    search_results = {}

    conn = get_db_connection()
    if not conn:
        return {item: [] for item in item_list}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            for item in item_list:
                cursor.execute("""
                    SELECT *
                    FROM food.menu_items
                    WHERE LOWER(name) = LOWER(%s)
                    ORDER BY review DESC NULLS LAST
                    LIMIT 3
                """, (item,))
                search_results[item] = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching food items from DB: {e}")
        for item in item_list:
            search_results[item] = []
    finally:
        conn.close()

    return search_results


def fetch_product_search_results(product_list):
    """Fetch product search results from server"""
    search_results = {}
    for product in product_list:
        try:
            search_url = f"{SERVER_URL}/search/product/{product}"
            r = requests.get(search_url)
            if r.status_code == 200:
                search_results[product] = r.json()
            else:
                search_results[product] = []
        except Exception as e:
            print(f"Error fetching product results for {product}: {e}")
            search_results[product] = []
    return search_results


def get_final_combined_selection(user_query, food_results, product_results):
    """Get final selection of items and products using AI"""
    system_prompt = """
    You are an intelligent assistant helping to select both food items and products for a user event (like birthday, picnic, trips etc.). You are given the user's request and available search results for both food items and products.

    Your job is to analyse the suitability of items and products based reviews, descriptions, and prices to fulfill the event requirements while staying within budget. And final output with the best item or product for each of the suggested items.

    Return only a JSON object with two arrays in the following format:
    {
        "food_selection": [
            {
                "item_name": "name of the 1st food item",
                "item_id": "ID of the 1st food item",
                "quantity": "number of items to order",
                "price": "price of this single item not multiplied by quantity",
                "reviews": "rating or reviews of the item",
                "restaurant_id": "ID of the restaurant as in the items data",
                "image_url": "URL of the food item image",
                "description": "brief description of the food item"
            },
            {
                "item_name": "name of the 2nd food item",
                "item_id": "ID of the 2nd food item",
                "quantity": "number of items to order",
                "price": "price of this single item not multiplied by quantity",
                "reviews": "rating or reviews of the item",
                "restaurant_id": "ID of the restaurant as in the items data",
                "image_url": "URL of the food item image",
                "description": "brief description of the food item"
            },
            //... rest of the food
        ],
        "product_selection": [
            {
                "product_name": "name of the 1st product",
                "product_id": "ID of the 1st product",
                "quantity": "number of products to order",
                "price": "price of this single product not multiplied by quantity",
                "reviews": "rating or reviews of the product",
                "category": "category of the product",
                "description": "brief description of the product"
                "producturl": "URL of the product image"
            },
            {
                "product_name": "name of the 2nd product",
                "product_id": "ID of the 2nd product",
                "quantity": "number of products to order",
                "price": "price of this single product not multiplied by quantity",
                "reviews": "rating or reviews of the product",
                "category": "category of the product",
                "description": "brief description of the product",
                "producturl": "URL of the product image"
            },
            //... rest of the products
        ]
    }
    
    Be budget-conscious, prioritize high reviews and variety.
    STRICT INSTRUCTIONS:
    - Do not include any additional text or explanations.
    - Do not repeat the same item from different restaurants.
    - Do not repeat the same product.
    - Ensure the output is a valid JSON object.
    - Consider the synergy between food and products for the event.
    - Preserve the data of the food items and products as provided in the search results.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Request: {user_query}\nAvailable Food Items: {food_results}\nAvailable Products: {product_results}"}
    ]

    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=messages,
        temperature=0,
        max_completion_tokens=1024,
        top_p=1,
        stream=False,
        stop=None,
    )

    import re

    selected_data = completion.choices[0].message.content.strip()
    print(f"Selected items and products: {selected_data}")

    # Step 1: Remove markdown formatting
    if selected_data.startswith("```json"):
        selected_data = selected_data.replace("```json", "").strip()
    elif selected_data.startswith("```"):
        selected_data = selected_data.replace("```", "").strip()
    if selected_data.endswith("```"):
        selected_data = selected_data[:-3].strip()

    # Step 2: Try to parse full string
    try:
        return json.loads(selected_data)
    except json.JSONDecodeError:
        print("Full JSON parsing failed. Trying to extract JSON block.")
        # Step 3: Extract JSON using regex
        match = re.search(r'\{.*\}', selected_data, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"Second JSON parse failed: {e}")
        # Step 4: Final fallback
        return {"food_selection": [], "product_selection": []}


@app.route("/chat/start", methods=["POST"])
def start_chat():
    data = request.get_json()
    user_query = data.get("query")

    if not user_query:
        return jsonify({"error": "Query is required"}), 400

    session_id = str(uuid4())
    session['session_id'] = session_id

    # Get initial suggestions
    available_food_items = fetch_available_food_items()
    available_products = fetch_available_products()
    suggestions = get_suggested_items_and_products(
        user_query, available_food_items, available_products)

    food_items = suggestions.get("food_items", [])
    products = suggestions.get("products", [])

    food_search_results = fetch_food_search_results(food_items)
    product_search_results = fetch_product_search_results(products)
    final_selection = get_final_combined_selection(
        user_query, food_search_results, product_search_results)

    # Store in session
    SESSION_CONTEXT[session_id] = {
        "chat_history": [{"role": "user", "content": user_query}],
        "food_items": food_items,
        "products": products,
        "food_search_results": food_search_results,
        "product_search_results": product_search_results,
        "final_selection": final_selection
    }

    return jsonify({
        "session_id": session_id,
        "initial_query": user_query,
        "suggestions": suggestions,
        "final_selection": final_selection
    })


@app.route("/chat/continue", methods=["POST"])
def continue_chat():
    data = request.get_json()
    session_id = data.get("session_id")
    followup_message = data.get("message")

    if not session_id or not followup_message:
        return jsonify({"error": "Session ID and message are required"}), 400

    context = SESSION_CONTEXT.get(session_id)
    if not context:
        return jsonify({"error": "Invalid session ID"}), 404

    # Update chat history
    context["chat_history"].append(
        {"role": "user", "content": followup_message})

    # Compose system + chat prompt for refinement
    system_prompt = """
    You are a helpful assistant refining food and product selections based on user follow-up instructions.
    Given the current selection and user instructions, return a revised version.

    Format:
    {
        "food_selection": [...],
        "product_selection": [...]
    }

    Do not repeat items unnecessarily.
    """

    # Combine prior context + follow-up message
    messages = [{"role": "system", "content": system_prompt}] + context["chat_history"] + [
        {"role": "user",
            "content": f"Current Selection:\n{json.dumps(context['final_selection'], indent=2)}"}
    ]

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            temperature=0.2,
            max_completion_tokens=1024,
            top_p=1,
        )

        revised = completion.choices[0].message.content.strip()
        revised_data = json.loads(revised)

        # Update context
        context["final_selection"] = revised_data
        context["chat_history"].append(
            {"role": "assistant", "content": revised})

        return jsonify({
            "revised_selection": revised_data,
            "chat_history": context["chat_history"]
        })

    except Exception as e:
        return jsonify({"error": "Failed to process revision", "details": str(e)})


@app.route("/cart/add-all", methods=["POST"])
def add_items_to_cart():
    """Add multiple food items to user's cart via external API"""
    data = request.get_json()
    food_selection = data.get("food_selection")
    # user_id = data.get("user_id")
    user_id = "5d320bcc-5ccd-4510-aace-695a3d864c18"

    if not food_selection or not user_id:
        return jsonify({"error": "Missing food_selection or user_id"}), 400

    added_items = []
    failed_items = []

    for item in food_selection:
        payload = {
            "user_id": user_id,
            "restaurant_id": item.get("restaurant_id"),
            "item_id": item.get("item_id"),
            "quantity": int(item.get("quantity", 1)),
            "producturl": item.get("producturl") or item.get("image_url"),
        }

        try:
            response = requests.post(f"{SERVER_URL}/cart/add", json=payload)
            if response.status_code == 200:
                added_items.append(payload)
            else:
                failed_items.append({"item": item, "reason": response.text})
        except Exception as e:
            failed_items.append({"item": item, "reason": str(e)})

    return jsonify({
        "status": "completed",
        "added": added_items,
        "failed": failed_items
    })


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "API is running"})


PORT = int(os.getenv("PORT", 8000))
if __name__ == "__main__":
    app.run(port=PORT, host="0.0.0.0")
