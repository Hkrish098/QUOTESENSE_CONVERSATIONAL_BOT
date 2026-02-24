import os
import time
import random
from dotenv import load_dotenv
from supabase import create_client
import googlemaps

#we need to load the environment files from the backend
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path = env_path)

#get keys from the env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY ,GOOGLE_MAPS_API_KEY ]):
    print(" the one of 3 keys is missing find the subpabase keys on supabase and google key in env and put it here!!.")
    exit()

#now initialize client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

#configuring to 100 rows not to exceed the limit and not burden the API

DAILY_BUDGET_COUNT = 1000
BATCH_SIZE = 50

TEST_LOCATIONS = [
    "Koramangala", 
    "HSR Layout", 
    "Marathahalli", 
    "JP Nagar", 
    "Banashankari", 
    "Jayanagar"
]

total_updated_this_run =0

def geocode_batch():
    global total_updated_this_run

    if total_updated_this_run >= DAILY_BUDGET_COUNT:
        return False
    
    # geo encoding for the 6 locations for now
    response = supabase.table("properties") \
        .select("listing_id, detailed_address, location") \
        .in_("location", TEST_LOCATIONS) \
        .is_("latitude", "null") \
        .limit(BATCH_SIZE) \
        .execute()
    
    rows = response.data

    if not rows:
        print("no more empty data for the coordinates in the selected 6 locations")
        print("to do the geo encoding for tomorrrow / for all locations just remove the TEST_LOCATION form the responce code.")

        return False
    
    for row in rows:
        # Check limit inside loop in case we hit it mid-batch
        if total_updated_this_run >= DAILY_BUDGET_COUNT:
            print(f" Reached daily limit of {DAILY_BUDGET_COUNT}. Stopping.")
            return False

        address = row['detailed_address']
        l_id = row['listing_id']
        area = row['location']

        try:
            #google maps API call
            result = gmaps.geocode(f"{address}, Bengaluru")

            if result:
                loc = result[0]['geometry']['location']
                lat, lng = loc['lat'], loc['lng']

                supabase.table("properties") \
                    .update({"latitude": lat, "longitude": lng}) \
                    .eq("listing_id", l_id) \
                    .execute()
                    
                total_updated_this_run += 1
                print(f"[{total_updated_this_run}/{DAILY_BUDGET_COUNT}] Updated {area}: {l_id} -> {lat}, {lng}")
            else:
                print(f" Skip: Could not find coordinates for {address}")

        except Exception as e:
            print(f"error on{l_id}:e")
            time.sleep(2)

        #now protect the API so keep a timer netween each call 
        time .sleep(random.uniform(0.6,1.2))


    return True

if __name__ == "__main__":
    print(f"🚀 Starting Test Batch for: {', '.join(TEST_LOCATIONS)}")
    print(f"Target: {DAILY_BUDGET_COUNT} rows.")
    
    while geocode_batch():
        print(f"--- Completed batch. Total so far: {total_updated_this_run} ---")
        
    print(f"🏁 Geocoding finished. Total properties updated: {total_updated_this_run}")

        