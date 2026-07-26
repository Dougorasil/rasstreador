import json
import subprocess
import time
import requests
from datetime import datetime
from typing import Dict, Any, Tuple

class LocationTracker:
    """
    Módulo de alta precisão GPS para Termux (Android).
    Força o uso exclusivo do GPS via hardware (Satélites) sem fallbacks fictícios por IP.
    Obtém telemetria avançada: Latitude, Longitude, Altitude, Velocidade, Rumos e Precisão em Metros.
    """
    def __init__(self, use_termux_api: bool = True, mock_fallback: bool = False):
        self.use_termux_api = use_termux_api
        self.mock_fallback = mock_fallback  # Desativado por padrão para EVITAR locais genéricos como SP
        self.last_known_address_cache = {}
        self.last_valid_location = None

    def get_raw_gps(self) -> Dict[str, Any]:
        """
        Obtém a localização via hardware GPS real do dispositivo Android (termux-location -p gps).
        Retorna dicionário com latitude, longitude, precisão, altitude, velocidade e provedor.
        """
        if self.use_termux_api:
            # 1ª Tentativa: GPS Hardware via Satélites (Precisão máxima)
            try:
                result = subprocess.run(
                    ["termux-location", "-p", "gps", "-s", "once"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    alt = float(data.get("altitude", 0.0))
                    speed = float(data.get("speed", 0.0))
                    bearing = float(data.get("bearing", 0.0))

                    if lat != 0.0 or lng != 0.0:
                        return {
                            "latitude": lat,
                            "longitude": lng,
                            "accuracy": acc,
                            "altitude": alt,
                            "speed": speed,
                            "bearing": bearing,
                            "provider": "gps_hardware",
                            "status": "fix_ok"
                        }
            except Exception:
                pass

            # 2ª Tentativa (se GPS satélite estiver sem visibilidade temporária indoor): Provedor Network do Android
            try:
                result = subprocess.run(
                    ["termux-location", "-p", "network", "-s", "once"],
                    capture_output=True,
                    text=True,
                    timeout=6
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    lat = float(data.get("latitude", 0.0))
                    lng = float(data.get("longitude", 0.0))
                    acc = float(data.get("accuracy", 0.0))
                    alt = float(data.get("altitude", 0.0))
                    speed = float(data.get("speed", 0.0))

                    if lat != 0.0 or lng != 0.0:
                        return {
                            "latitude": lat,
                            "longitude": lng,
                            "accuracy": acc,
                            "altitude": alt,
                            "speed": speed,
                            "bearing": 0.0,
                            "provider": "network_triangulation",
                            "status": "fix_ok"
                        }
            except Exception:
                pass

        # Se houver uma localização válida anterior capturada pelo GPS físico, mantém ela em vez de inventar
        if self.last_valid_location:
            loc = dict(self.last_valid_location)
            loc["status"] = "aguardando_novo_sinal"
            return loc

        # Se nenhuma localização real for capturada e o mock estiver explicitamente ativado para dev no PC
        if self.mock_fallback:
            return {
                "latitude": -23.550520,
                "longitude": -46.633308,
                "accuracy": 15.0,
                "altitude": 760.0,
                "speed": 0.0,
                "bearing": 0.0,
                "provider": "simulacao_pc",
                "status": "mock"
            }

        return {
            "latitude": 0.0,
            "longitude": 0.0,
            "accuracy": 0.0,
            "altitude": 0.0,
            "speed": 0.0,
            "bearing": 0.0,
            "provider": "sem_sinal_gps",
            "status": "sem_fix"
        }

    def reverse_geocode(self, lat: float, lng: float) -> Dict[str, str]:
        """
        Realiza geocodificação reversa de alta precisão (zoom=18).
        """
        if lat == 0.0 and lng == 0.0:
            return {
                "street": "Aguardando Sinal de GPS",
                "neighborhood": "Ative o GPS do celular",
                "city": "Aguardando Fix",
                "state": "--",
                "postcode": "",
                "full_address": "Sinal de GPS do dispositivo não capturado. Certifique-se de que a Localização/GPS do Android está ATIVADA."
            }

        cache_key = f"{round(lat, 5)},{round(lng, 5)}"
        if cache_key in self.last_known_address_cache:
            return self.last_known_address_cache[cache_key]

        headers = {
            "User-Agent": "TermuxRastreadorGPS/3.0 (hardware-gps)"
        }
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"

        address_info = {
            "street": "Rua não identificada",
            "neighborhood": "Bairro não identificado",
            "city": "Cidade não identificada",
            "state": "UF",
            "postcode": "",
            "full_address": f"Lat: {lat:.7f}, Lng: {lng:.7f}"
        }

        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address", {})

                house_num = addr.get("house_number", "")
                road = addr.get("road") or addr.get("pedestrian") or addr.get("street") or addr.get("avenue") or addr.get("footway") or "Rua não identificada"
                
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
        except Exception:
            pass

        return address_info

    def capture_location(self) -> Dict[str, Any]:
        """
        Executa o processo de leitura do GPS real e montagem dos dados de telemetria.
        """
        gps_data = self.get_raw_gps()
        lat = gps_data["latitude"]
        lng = gps_data["longitude"]

        if lat != 0.0 and lng != 0.0:
            self.last_valid_location = gps_data

        addr = self.reverse_geocode(lat, lng)
        
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        google_maps_url = f"https://www.google.com/maps?q={lat:.7f},{lng:.7f}" if (lat != 0.0 or lng != 0.0) else ""

        return {
            "latitude": lat,
            "longitude": lng,
            "accuracy": gps_data["accuracy"],
            "altitude": gps_data["altitude"],
            "speed": gps_data["speed"],
            "bearing": gps_data["bearing"],
            "provider": gps_data["provider"],
            "status_fix": gps_data["status"],
            "street": addr["street"],
            "neighborhood": addr["neighborhood"],
            "city": addr["city"],
            "state": addr["state"],
            "postcode": addr.get("postcode", ""),
            "full_address": addr["full_address"],
            "google_maps_url": google_maps_url,
            "last_updated": now_str
        }
