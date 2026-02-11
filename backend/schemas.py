from pydantic import BaseModel
from typing import Optional

class RentalState(BaseModel):
    # Bucket 1: The Essentials
    size_bhk: int = 0
    total_sqft: float = 0.0
    location_name: Optional[str] = None
    
    # Bucket 2: Structural Details
    bath: int = 2 
    balcony: int = 1
    furnishing: int = 1 # 1: Semi-furnished
    
    # Bucket 3 & 4: Amenities & Index
    location_premium_index: float = 21.0
    gym_nearby: int = 0
    has_ac: int = 0
    zone_East: int = 0
    zone_North: int = 0
    zone_South: int = 0
    zone_West: int = 0
    
    # Conversation State
    stage: str = "collecting"