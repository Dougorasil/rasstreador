import os
import json
import requests
import hashlib
from typing import Dict, Any, Optional, List

class FirebaseService:
    """
    Serviço robusto de comunicação com o Firebase Realtime Database usando a API REST
    com relatórios claros de erros e suporte a token OAuth2 / Service Account.
    """
    def __init__(self, database_url: str, api_key: str = "", service_account_file: str = ""):
        self.database_url = database_url.rstrip("/")
        self.api_key = api_key
        self.service_account_file = service_account_file
        self.creds = None

        if not self.service_account_file:
            default_sa_paths = [
                os.path.join(os.path.dirname(__file__), "service_account.json"),
                os.path.join(os.path.dirname(__file__), "..", "rastreador-c229f-firebase-adminsdk-fbsvc-51dd7209d5.json")
            ]
            for p in default_sa_paths:
                if os.path.exists(p):
                    self.service_account_file = os.path.abspath(p)
                    break

        self._init_service_account()

    def _init_service_account(self):
        if self.service_account_file and os.path.exists(self.service_account_file):
            try:
                from google.oauth2 import service_account
                scopes = [
                    "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/firebase.database"
                ]
                self.creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, scopes=scopes
                )
            except Exception:
                pass

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.creds:
            try:
                import google.auth.transport.requests
                if not self.creds.valid:
                    self.creds.refresh(google.auth.transport.requests.Request())
                headers["Authorization"] = f"Bearer {self.creds.token}"
            except Exception:
                pass
        return headers

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Autentica o usuário no Firebase RTDB.
        Retorna o dicionário do usuário em caso de sucesso, ou dict contendo {'error': 'motivo'}.
        """
        clean_user = username.strip().lower()
        url = f"{self.database_url}/users/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                user_data = res.json()
                if not user_data:
                    return {"error": f"Usuário '{clean_user}' não encontrado."}
                
                password_hash = self._hash_password(password)
                if user_data.get("password") == password_hash:
                    if not user_data.get("active", True):
                        return {"error": "Esta conta foi desativada pelo administrador."}
                    return user_data
                else:
                    return {"error": "Senha incorreta!"}
            elif res.status_code in [401, 403]:
                return {"error": f"Erro de Permissão no Firebase (HTTP {res.status_code}). Verifique se as Regras do Realtime Database estão liberadas (.read: true, .write: true)."}
            else:
                return {"error": f"Falha na comunicação com o Firebase (HTTP {res.status_code})."}
        except Exception as e:
            return {"error": f"Erro de conexão com o Firebase: {e}"}

    def create_user(self, username: str, password: str, name: str, role: str = "user") -> bool:
        clean_user = username.strip().lower()
        url = f"{self.database_url}/users/{clean_user}.json"
        
        user_payload = {
            "username": clean_user,
            "name": name,
            "password": self._hash_password(password),
            "role": role,
            "active": True,
            "tracking_enabled": False
        }
        
        try:
            headers = self._get_headers()
            res = requests.put(url, json=user_payload, headers=headers, timeout=10)
            if res.status_code in [200, 201]:
                loc_url = f"{self.database_url}/locations/{clean_user}.json"
                requests.patch(loc_url, json={
                    "username": clean_user,
                    "name": name,
                    "monitoring_active": False,
                    "last_updated": "Nunca"
                }, headers=headers, timeout=5)
                return True
        except Exception as e:
            print(f"[!] Erro ao criar usuário no Firebase: {e}")
        return False

    def update_location(self, username: str, loc_data: Dict[str, Any]) -> bool:
        clean_user = username.strip().lower()
        url = f"{self.database_url}/locations/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.patch(url, json=loc_data, headers=headers, timeout=5)
            return res.status_code in [200, 201]
        except Exception as e:
            print(f"[!] Erro ao enviar localização: {e}")
            return False

    def toggle_monitoring(self, username: str, status: bool) -> bool:
        clean_user = username.strip().lower()
        user_url = f"{self.database_url}/users/{clean_user}.json"
        loc_url = f"{self.database_url}/locations/{clean_user}.json"
        try:
            headers = self._get_headers()
            requests.patch(user_url, json={"tracking_enabled": status}, headers=headers, timeout=5)
            requests.patch(loc_url, json={"monitoring_active": status}, headers=headers, timeout=5)
            return True
        except Exception as e:
            print(f"[!] Erro ao alterar status: {e}")
            return False

    def get_all_users(self) -> List[Dict[str, Any]]:
        url = f"{self.database_url}/users.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200 and res.json():
                return list(res.json().values())
        except Exception as e:
            print(f"[!] Erro ao buscar usuários: {e}")
        return []

    def get_all_locations(self) -> Dict[str, Any]:
        url = f"{self.database_url}/locations.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200 and res.json():
                return res.json()
        except Exception as e:
            print(f"[!] Erro ao buscar localizações: {e}")
        return {}

    def ensure_default_admin(self):
        clean_user = "admin"
        url = f"{self.database_url}/users/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and not res.json():
                print("[*] Criando conta de administrador padrão: admin / admin123")
                self.create_user("admin", "admin123", "Administrador Geral", role="admin")
        except Exception:
            pass
