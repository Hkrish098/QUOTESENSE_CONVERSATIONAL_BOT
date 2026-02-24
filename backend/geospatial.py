import googlemaps
import os

# Initialize Google Maps client
gmaps = googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))

def get_coordinates(location_name):
    """
    Converts address to Lat/Lng using Google Geocoding API.
    """
    try:
        # We target Bengaluru specifically
        geocode_result = gmaps.geocode(f"{location_name}, Bengaluru")
        
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return {"lat": location['lat'], "lng": location['lng']}
        return None
    except Exception as e:
        print(f"Google Geocoding Error: {e}")
        return None