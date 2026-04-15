'use client';

import React, { useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup } from 'react-leaflet';
import { colors } from '@agroamigo/shared';
import colombiaGeoJson from '@agroamigo/shared/data/colombia-departments.json';
import 'leaflet/dist/leaflet.css';

function interpolateColor(value: number, min: number, max: number, colorScale: string[]): string {
  if (max === min) return colorScale[3];
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const idx = Math.min(Math.floor(t * (colorScale.length - 1)), colorScale.length - 2);
  return colorScale[idx + 1];
}

interface Props {
  mode: 'price' | 'supply';
  divipolaToValue: Map<string, number>;
  minVal: number;
  maxVal: number;
  colorScale: string[];
  markets: any[];
  onMarketClick: (id: string) => void;
}

export default function MapComponent({ mode, divipolaToValue, minVal, maxVal, colorScale, markets, onMarketClick }: Props) {
  const geoJsonStyle = useMemo(() => {
    return (feature: any) => {
      const code = feature?.properties?.DPTO;
      const value = code ? divipolaToValue.get(code) : undefined;
      const fillColor = value != null && value > 0
        ? interpolateColor(value, minVal, maxVal, colorScale)
        : '#E0E0E0';
      return { fillColor, fillOpacity: 0.7, color: '#FFFFFF', weight: 1.5 };
    };
  }, [divipolaToValue, minVal, maxVal, colorScale]);

  return (
    <MapContainer center={[4.5, -73.0]} zoom={5} style={{ flex: 1, width: '100%', minHeight: 400 }} zoomControl={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <GeoJSON data={colombiaGeoJson as any} style={geoJsonStyle} />
      {markets.map((m: any) => (
        <CircleMarker key={m.id} center={[m.lat, m.lng]} radius={5} pathOptions={{ color: colors.primary, fillColor: colors.primary, fillOpacity: 0.8 }}
          eventHandlers={{ click: () => onMarketClick(m.id) }}>
          <Popup><strong>{m.name}</strong><br />{m.city}, {m.department}</Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
