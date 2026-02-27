"use client";
import React, { useEffect } from 'react';
import { APIProvider, Map, AdvancedMarker, Pin, useMap } from '@vis.gl/react-google-maps';

// --- UPDATED COMPONENT: Draws the Search Area (Box or Polygon) ---
const BoundaryDrawing = ({ hubs, searchZone }) => {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    let drawing = null;

    // IF BACKEND SENT A SPECIFIC SEARCH ZONE (The Emerald Box)
    if (searchZone) {
      drawing = new window.google.maps.Rectangle({
        bounds: {
          north: searchZone.max_lat,
          south: searchZone.min_lat,
          east: searchZone.max_lng,
          west: searchZone.min_lng,
        },
        strokeColor: "#10b981",
        strokeOpacity: 0.8,
        strokeWeight: 2,
        fillColor: "#10b981",
        fillOpacity: 0.15,
      });
    } 
    // FALLBACK: If we just have raw hubs (Legacy mode)
    else if (hubs.length >= 3) {
      drawing = new window.google.maps.Polygon({
        paths: hubs.map(h => ({ lat: parseFloat(h.lat), lng: parseFloat(h.lng) })),
        strokeColor: "#10b981",
        strokeOpacity: 0.8,
        strokeWeight: 2,
        fillColor: "#10b981",
        fillOpacity: 0.15,
      });
    }

    if (drawing) drawing.setMap(map);

    return () => { if (drawing) drawing.setMap(null); };
  }, [map, hubs, searchZone]);

  return null;
};

const MapHandler = ({ hubs, properties }) => {
  const map = useMap();

  useEffect(() => {
    if (!map || (hubs.length === 0 && properties.length === 0)) return;

    const bounds = new window.google.maps.LatLngBounds();
    let validPoints = 0;

    hubs.forEach(h => {
      if (h.lat && h.lng) {
        bounds.extend({ lat: parseFloat(h.lat), lng: parseFloat(h.lng) });
        validPoints++;
      }
    });

    properties.forEach(p => {
      if (p.latitude && p.longitude) {
        bounds.extend({ lat: parseFloat(p.latitude), lng: parseFloat(p.longitude) });
        validPoints++;
      }
    });

    if (validPoints > 0) {
      map.fitBounds(bounds, 80);
    }
  }, [map, hubs, properties]);

  return null;
};

export default function MidpointMap({ familyHubs = [], properties = [], searchZone = null }) {
  const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

  if (!API_KEY) {
    console.error("Map Error: NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is undefined");
    return <div className="p-4 text-red-500 font-bold">Config Error: API Key Missing</div>;
  }

  return (
    <APIProvider apiKey={API_KEY}>
      <div className="w-full h-full min-h-[400px]">
        <Map
          // Dynamically centers on the midpoint box if provided, else defaults to Bengaluru
          defaultCenter={searchZone?.center || { lat: 12.9716, lng: 77.5946 }}
          defaultZoom={13}
          mapId="959fda172119073bff5d1371" 
          gestureHandling={'greedy'}
          disableDefaultUI={true}
        >
          {/* Draws the green area based on the search_zone box from backend */}
          <BoundaryDrawing hubs={familyHubs} searchZone={searchZone} />
          
          <MapHandler hubs={familyHubs} properties={properties} />

          {/* Hub Markers (Red) - Workplaces or Study Centers */}
          {familyHubs.map((hub, idx) => (
            <AdvancedMarker key={`hub-${idx}`} position={{ lat: parseFloat(hub.lat), lng: parseFloat(hub.lng) }}>
              <Pin background={'#ef4444'} glyphColor={'#fff'} borderColor={'#000'} />
              <div className="bg-white/90 p-1 px-2 rounded shadow text-[10px] font-bold mt-1 text-black whitespace-nowrap">
                🏢 {hub.label}
              </div>
            </AdvancedMarker>
          ))}

          {/* Property Markers (Green) - Individual Home Results */}
          {properties.map((prop, idx) => {
            if (!prop.latitude || !prop.longitude) return null;
            return (
              <AdvancedMarker
                key={`prop-${idx}`} 
                position={{ lat: parseFloat(prop.latitude), lng: parseFloat(prop.longitude) }}
              >
                <Pin background={'#10b981'} glyphColor={'#fff'} scale={0.9} />
              </AdvancedMarker>
            );
          })}
        </Map>
      </div>
    </APIProvider>
  );
}