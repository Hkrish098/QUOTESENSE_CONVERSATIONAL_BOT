import os
import time
import random
from dotenv import load_dotenv
from supabase import create_client
import googlemaps

# 1. LOAD ENV FROM BACKEND FOLDER
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

# 2. GET KEYS FROM ENV
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_MAPS_API_KEY]):
    print("❌ Error: Missing API keys in .env file.")
    exit()

# 3. INITIALIZE CLIENTS
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# --- CONFIGURATION ---
DAILY_BUDGET_COUNT = 1500  # Will process 1000 rows today
BATCH_SIZE = 50            # Fetch 50 at a time
total_updated_this_run = 0

def geocode_batch():
    global total_updated_this_run

    if total_updated_this_run >= DAILY_BUDGET_COUNT:
        return False
    
    # --- CHANGE MADE HERE: Removed the .in_("location", TEST_LOCATIONS) filter ---
    # This now targets ANY row in ANY location where latitude is null
    response = supabase.table("properties") \
        .select("listing_id, detailed_address, location") \
        .is_("latitude", "null") \
        .limit(BATCH_SIZE) \
        .execute()
    
    rows = response.data

    if not rows:
        print("✅ SUCCESS: All properties in the database are now geocoded!")
        return False
    
    for row in rows:
        if total_updated_this_run >= DAILY_BUDGET_COUNT:
            print(f"🛑 Reached daily limit of {DAILY_BUDGET_COUNT}. Stopping.")
            return False

        address = row['detailed_address']
        l_id = row['listing_id']
        area = row['location']

        try:
            # Google Maps API call
            result = gmaps.geocode(f"{address}, Bengaluru")

            if result:
                loc = result[0]['geometry']['location']
                lat, lng = loc['lat'], loc['lng']

                # Update the row in Supabase
                supabase.table("properties") \
                    .update({"latitude": lat, "longitude": lng}) \
                    .eq("listing_id", l_id) \
                    .execute()
                    
                total_updated_this_run += 1
                print(f"[{total_updated_this_run}/{DAILY_BUDGET_COUNT}] Updated {area}: {l_id}")
            else:
                print(f"⚠️ Skip: Could not find coordinates for {address}")

        except Exception as e:
            print(f"❌ Error on {l_id}: {e}")
            time.sleep(2)

        # Protect API with random delay
        time.sleep(random.uniform(0.6, 1.2))

    return True

if __name__ == "__main__":
    print(f"🚀 Starting Production Geocoding for ALL Bengaluru locations...")
    print(f"Targeting {DAILY_BUDGET_COUNT} properties for this run.")
    
    while geocode_batch():
        print(f"--- Batch complete. Total updated so far: {total_updated_this_run} ---")
        
    print(f"🏁 Geocoding finished. Total properties updated: {total_updated_this_run}")