import json
import subprocess
import time
import requests
from datetime import datetime
from typing import Dict, Any, Tuple

class LocationTracker:
    """
    Módulo otimizado de rastreamento de localização para Termux (Android) e Desktop.
    Tenta obter coordenadas GPS brutas de alta precisão usando 'gps' e 'network',
    realizando geocodificação reversa detalhada (Rua, Número, Bairro, Cidade, CEP, Link Google Maps).
    """
    def __init__(self, use_termux_api: bool = True, mock_fallback: bool = True):
        self.use_termux_api = use_termux_api
        self.mock_fallback = mock_fallback
        self.last_known_address_cache = {}

    def get_raw_gps(self) -> Tuple[float, float, float, str]:
        """
        Tenta obter coordenadas GPS de alta precisão.
        Testa primeiro o provedor 'gps' (satélite) e faz fallback inteligente para 'network' (Wi-Fi/Torres).
        Retorna (latitude, longitude, precisao_metros, provedor_usado).
        """
        if self.use_termux_api:
            # 1ª Tentativa: GPS por Satélite (Termux API)
            try:
                result = subprocess.run(
                    ["termux-location", "-p", "gps", "-s", "once"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    if lat != 0.0 or lng != 0.0:
                        return (lat, lng, acc, "gps")
            except Exception:
                pass

            # 2ª Tentativa: Provedor de Rede / Wi-Fi (Network - Instantâneo e preciso para locais cobertos)
            try:
                result = subprocess.run(
                    ["termux-location", "-p", "network", "-s", "once"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    if lat != 0.0 or lng != 0.0:
                        return (lat, lng, acc, "network")
            except Exception:
                pass

            # 3ª Tentativa: Chamada genérica termux-location sem filtro
            try:
                result = subprocess.run(
                    ["termux-location"],
                    capture_output=True,
                    text=True,
                    timeout=4
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    if lat != 0.0 or lng != 0.0:
                        return (lat, lng, acc, data.get("provider", "termux-default"))
            except Exception:
                pass

        if self.mock_fallback:
            # Fallback via IP (Apenas se o GPS do celular não estiver disponível ou rodando no PC)
            try:
                res = requests.get("https://ipapi.co/json/", timeout=4).json()
                lat = float(res.get("latitude", -23.5505))
                lng = float(res.get("longitude", -46.6333))
                return (lat, lng, 15.0, "ip-geolocation")
            except Exception:
                return (-23.550520, -46.633308, 10.0, "mock-fallback")

        return (0.0, 0.0, 0.0, "desconhecido")

    def reverse_geocode(self, lat: float, lng: float) -> Dict[str, str]:
        """
        Converte coordenadas (lat, lng) no endereço exato com alta precisão (zoom=18).
        Obtém Rua, Número, Bairro, Cidade, Estado e CEP via OpenStreetMap Nominatim.
        """
        cache_key = f"{round(lat, 5)},{round(lng, 5)}"
        if cache_key in self.last_known_address_cache:
            return self.last_known_address_cache[cache_key]

        headers = {
            "User-Agent": "TermuxRastreadorGPS/2.0 (contact@local.dev)"
        }
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"

        address_info = {
            "street": "Rua não identificada",
            "neighborhood": "Bairro não identificado",
            "city": "Cidade não identificada",
            "state": "UF",
            "postcode": "",
            "full_address": f"Lat: {lat}, Lng: {lng}"
        }

        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address", {})

                house_num = addr.get("house_number", "")
                road = addr.get("road") or addr.get("pedestrian") or addr.get("street") or addr.get("avenue") or addr.get("footway") or addr.get("path") or "Rua não identificada"
                
                street_display = f"{road}, {house_num}" if house_num and road != "Rua não identificada" else road

                neighborhood = addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter") or addr.get("residential") or "Bairro não identificado"
                city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("village") or addr.get("county") or "Cidade não identificada"
                state = addr.get("state") or addr.get("state_code") or ""
                postcode = addr.get("postcode") or ""

                address_info = {
                    "street": street_display,
                    "neighborhood": neighborhood,
                    "city": city,
                    "state": state,
                    "postcode": postcode,
                    "full_address": data.get("display_name", f"{street_display}, {neighborhood} - {city}")
                }
                self.last_known_address_cache[cache_key] = address_info
        except Exception as e:
            pass

        return address_info

    def capture_location(self) -> Dict[str, Any]:
        """
        Executa o fluxo completo:
        1. Obtém GPS exato
        2. Realiza a geocodificação reversa detalhada
        3. Monta link direto do Google Maps e timestamp oficial
        """
        lat, lng, acc, provider = self.get_raw_gps()
        addr = self.reverse_geocode(lat, lng)
        
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        google_maps_url = f"https://www.google.com/maps?q={lat:.7f},{lng:.7f}"

        return {
            "latitude": lat,
            "longitude": lng,
            "accuracy": acc,
            "provider": provider,
            "street": addr["street"],
            "neighborhood": addr["neighborhood"],
            "city": addr["city"],
            "state": addr["state"],
            "postcode": addr.get("postcode", ""),
            "full_address": addr["full_address"],
            "google_maps_url": google_maps_url,
            "last_updated": now_str
        }
