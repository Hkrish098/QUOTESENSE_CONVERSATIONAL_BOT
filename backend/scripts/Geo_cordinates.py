import os
import time
import random
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.client import ClientOptions
import googlemaps

# 1. LOAD ENV
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# 2. INITIALIZE
opts = ClientOptions(postgrest_client_timeout=60)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=opts)
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# --- CONFIGURATION ---
DAILY_BUDGET_COUNT = 1500  
BATCH_SIZE = 50            
total_updated_this_run = 0
last_processed_id = "" # Tracks progress through the table

def geocode_batch():
    global total_updated_this_run, last_processed_id

    if total_updated_this_run >= DAILY_BUDGET_COUNT:
        return False
    
    # 🎯 STEP 1: Fetch by ID order (Instant/No Timeout)
    try:
        query = supabase.table("properties").select("listing_id, detailed_address, location, latitude").order("listing_id")
        
        # If we have a last_id, start from the next one
        if last_processed_id:
            query = query.gt("listing_id", last_processed_id)
            
        response = query.limit(BATCH_SIZE).execute()
        rows = response.data
    except Exception as e:
        print(f"❌ Supabase Fetch Error: {e}")
        return False

    if not rows:
        print("✅ Reached the end of the database table.")
        return False
    
    # Update our tracker to the last ID in this batch
    last_processed_id = rows[-1]['listing_id']
    
    # 🎯 STEP 2: Filter in Python (Fast)
    pending_rows = [r for r in rows if r['latitude'] is None or r['latitude'] == 0 or r['latitude'] == ""]

    if not pending_rows:
        print(f"⏭️ Batch ({rows[0]['listing_id']} to {rows[-1]['listing_id']}) already geocoded. Skipping...")
        return True 

    # 🎯 STEP 3: Process only the empty rows
    for row in pending_rows:
        if total_updated_this_run >= DAILY_BUDGET_COUNT:
            return False

        l_id = row['listing_id']
        query_address = f"{row['detailed_address']}, {row['location']}, Bengaluru, Karnataka"

        try:
            result = gmaps.geocode(query_address)
            if result:
                loc = result[0]['geometry']['location']
                supabase.table("properties").update({
                    "latitude": loc['lat'], 
                    "longitude": loc['lng']
                }).eq("listing_id", l_id).execute()
                
                total_updated_this_run += 1
                print(f"[{total_updated_this_run}] ✅ Updated: {l_id}")
            else:
                # Mark as 0.0001 so it's "not null" but clearly failed
                supabase.table("properties").update({"latitude": 0.0001}).eq("listing_id", l_id).execute()
                print(f"⚠️ Skip: {l_id} - Not found by Google.")

        except Exception as e:
            print(f"❌ API Error on {l_id}: {e}")
            time.sleep(2)

        time.sleep(random.uniform(0.5, 0.8))

    return True

if __name__ == "__main__":
    print(f"🚀 Starting ID-Based Geocoding (Timeout Proof)...")
    try:
        while geocode_batch():
            pass
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    print(f"🏁 Process finished. Total updated: {total_updated_this_run}")