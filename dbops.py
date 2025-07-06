import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig:
    """Database configuration and connection management"""

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = os.getenv("DB_PORT", "5432")
        self.database = os.getenv("DB_NAME")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")

    def get_connection(self):
        """Create and return a database connection"""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            return conn
        except psycopg2.Error as e:
            print(f"Database connection error: {e}")
            return None

    def test_connection(self):
        """Test database connection"""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    conn.close()
                    return True
            except psycopg2.Error as e:
                print(f"Database test error: {e}")
                return False
        return False


class DatabaseOperations:
    """Database operations for fetching products and food items"""

    def __init__(self, db_config):
        self.db_config = db_config

    def fetch_available_products(self):
        """Fetch available product names from database"""
        conn = self.db_config.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT name FROM products.productitem GROUP BY name ORDER BY name")
                result = cursor.fetchall()
                return [row['name'] for row in result]
        except psycopg2.Error as e:
            print(f"Error fetching products: {e}")
            return []
        finally:
            conn.close()

    def fetch_available_food_items(self):
        """Fetch available food item names from database"""
        conn = self.db_config.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT name FROM food.menu_items GROUP BY name ORDER BY name")
                result = cursor.fetchall()
                return [row['name'] for row in result]
        except psycopg2.Error as e:
            print(f"Error fetching food items: {e}")
            return []
        finally:
            conn.close()

    def get_product_details(self, product_name):
        """Get detailed information about a specific product"""
        conn = self.db_config.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM products.productitem 
                    WHERE name = %s 
                    LIMIT 1
                """, (product_name,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error fetching product details for {product_name}: {e}")
            return None
        finally:
            conn.close()

    def get_food_item_details(self, food_name):
        """Get detailed information about a specific food item"""
        conn = self.db_config.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM food.menu_items 
                    WHERE name = %s 
                    LIMIT 1
                """, (food_name,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error fetching food item details for {food_name}: {e}")
            return None
        finally:
            conn.close()

    def get_available_categories(self):
        """Get available product categories"""
        conn = self.db_config.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT DISTINCT category FROM products.productitem 
                    WHERE category IS NOT NULL 
                    ORDER BY category
                """)
                result = cursor.fetchall()
                return [row['category'] for row in result]
        except psycopg2.Error as e:
            print(f"Error fetching categories: {e}")
            return []
        finally:
            conn.close()

    def get_products_by_category(self, category):
        """Get products by category"""
        conn = self.db_config.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT name FROM products.productitem 
                    WHERE category = %s 
                    GROUP BY name 
                    ORDER BY name
                """, (category,))
                result = cursor.fetchall()
                return [row['name'] for row in result]
        except psycopg2.Error as e:
            print(f"Error fetching products by category {category}: {e}")
            return []
        finally:
            conn.close()
