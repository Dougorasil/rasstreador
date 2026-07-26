import json
import subprocess
import time
import requests
from datetime import datetime
from typing import Dict, Any, Tuple

class LocationTracker:
    """
    Módulo responsável pela captura de GPS no Termux (via termux-location)
    e pela conversão em endereço exato (Geocodificação Reversa) com link do Google Maps.
    """
    def __init__(self, use_termux_api: bool = True, mock_fallback: bool = True):
        self.use_termux_api = use_termux_api
        self.mock_fallback = mock_fallback
        self.last_known_address_cache = {}

    def get_raw_gps(self) -> Tuple[float, float, float]:
        """
        Tenta obter coordenadas GPS brutas (latitude, longitude, precisão).
        Retorna (lat, lng, accuracy).
        """
        if self.use_termux_api:
            try:
                # Executa o comando do Termux API para pegar a localização atual
                result = subprocess.run(
                    ["termux-location", "-p", "gps", "-s", "once"],
                    capture_output=True,
                    text=True,
                    timeout=8
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    if lat != 0.0 or lng != 0.0:
                        return (lat, lng, acc)
            except Exception as e:
                # Caso falhe a chamada do termux-location
                pass

        if self.mock_fallback:
            # Fallback para testes em PC ou quando a API do Termux não responde
            try:
                ip_info = requests.get("https://ipapi.co/json/", timeout=4).json()
                lat = float(ip_info.get("latitude", -23.5505))
                lng = float(ip_info.get("longitude", -46.6333))
                return (lat, lng, 15.0)
            except Exception:
                # Coordenada padrão de fallback (Ex: São Paulo)
                return (-23.550520, -46.633308, 10.0)

        return (0.0, 0.0, 0.0)

    def reverse_geocode(self, lat: float, lng: float) -> Dict[str, str]:
        """
        Converte latitude e longitude no endereço detalhado:
        Rua, Bairro, Cidade, Estado, CEP.
        Utiliza OpenStreetMap (Nominatim API).
        """
        cache_key = f"{round(lat, 4)},{round(lng, 4)}"
        if cache_key in self.last_known_address_cache:
            return self.last_known_address_cache[cache_key]

        headers = {
            "User-Agent": "TermuxRastreadorApp/1.0 (contact@local.dev)"
        }
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"

        address_info = {
            "street": "Rua não identificada",
            "neighborhood": "Bairro não identificado",
            "city": "Cidade não identificada",
            "state": "UF",
            "full_address": "Endereço não disponível"
        }

        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address", {})

                street = addr.get("road") or addr.get("pedestrian") or addr.get("suburb") or "Rua não identificada"
                neighborhood = addr.get("neighbourhood") or addr.get("suburb") or addr.get("residential") or "Bairro não identificado"
                city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("village") or "Cidade não identificada"
                state = addr.get("state") or addr.get("state_code") or ""

                address_info = {
                    "street": street,
                    "neighborhood": neighborhood,
                    "city": city,
                    "state": state,
                    "full_address": data.get("display_name", f"{street}, {neighborhood}")
                }
                self.last_known_address_cache[cache_key] = address_info
        except Exception:
            pass

        return address_info

    def capture_location(self) -> Dict[str, Any]:
        """
        Executa o processo completo de captura, geocodificação e montagem do pacote de dados.
        """
        lat, lng, acc = self.get_raw_gps()
        addr = self.reverse_geocode(lat, lng)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        google_maps_url = f"https://www.google.com/maps?q={lat},{lng}"

        return {
            "latitude": lat,
            "longitude": lng,
            "accuracy": acc,
            "street": addr["street"],
            "neighborhood": addr["neighborhood"],
            "city": addr["city"],
            "state": addr["state"],
            "full_address": addr["full_address"],
            "google_maps_url": google_maps_url,
            "last_updated": now_str
        }
