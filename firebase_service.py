import os
import json
import requests
import hashlib
from typing import Dict, Any, Optional, List

class FirebaseService:
    """
    Serviço de comunicação com o Firebase Realtime Database usando a API REST
    e suporte a Autenticação via Conta de Serviço (Service Account JSON) ou Acesso Direto.
    """
    def __init__(self, database_url: str, api_key: str = "", service_account_file: str = ""):
        self.database_url = database_url.rstrip("/")
        self.api_key = api_key
        self.service_account_file = service_account_file
        self.creds = None

        # Tenta carregar credenciais da Service Account se o arquivo existir
        if not self.service_account_file:
            # Procura o arquivo .json da service account na pasta pai ou atual
            default_sa_paths = [
                os.path.join(os.path.dirname(__file__), "..", "rastreador-c229f-firebase-adminsdk-fbsvc-51dd7209d5.json"),
                os.path.join(os.path.dirname(__file__), "service_account.json")
            ]
            for p in default_sa_paths:
                if os.path.exists(p):
                    self.service_account_file = os.path.abspath(p)
                    break

        self._init_service_account()

    def _init_service_account(self):
        """Inicializa o objeto de credenciais do Google se a Service Account estiver presente."""
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
            except Exception as e:
                # Caso a biblioteca google-auth não esteja instalada no Termux, usa REST direto
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
        """Gera um hash SHA-256 da senha."""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Autentica o usuário pelo nome de usuário e senha."""
        clean_user = username.strip().lower()
        url = f"{self.database_url}/users/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200 and res.json():
                user_data = res.json()
                password_hash = self._hash_password(password)
                if user_data.get("password") == password_hash:
                    if not user_data.get("active", True):
                        return {"error": "Conta desativada pelo administrador."}
                    return user_data
        except Exception as e:
            print(f"[!] Erro ao conectar ao Firebase: {e}")
        return None

    def create_user(self, username: str, password: str, name: str, role: str = "user") -> bool:
        """Cria um novo usuário no Firebase."""
        clean_user = username.strip().lower()
        url = f"{self.database_url}/users/{clean_user}.json"
        
        user_payload = {
            "username": clean_user,
            "name": name,
            "password": self._hash_password(password),
            "role": role, # 'admin' ou 'user'
            "active": True,
            "tracking_enabled": False
        }
        
        try:
            headers = self._get_headers()
            res = requests.put(url, json=user_payload, headers=headers, timeout=10)
            if res.status_code in [200, 201]:
                # Inicializa a estrutura de localização
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
        """Atualiza a localização exata do usuário no nó /locations/{username}."""
        clean_user = username.strip().lower()
        url = f"{self.database_url}/locations/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.patch(url, json=loc_data, headers=headers, timeout=5)
            return res.status_code in [200, 201]
        except Exception as e:
            print(f"[!] Erro ao enviar localização para o Firebase: {e}")
            return False

    def toggle_monitoring(self, username: str, status: bool) -> bool:
        """Ativa ou desativa o monitoramento para o usuário."""
        clean_user = username.strip().lower()
        user_url = f"{self.database_url}/users/{clean_user}.json"
        loc_url = f"{self.database_url}/locations/{clean_user}.json"
        try:
            headers = self._get_headers()
            requests.patch(user_url, json={"tracking_enabled": status}, headers=headers, timeout=5)
            requests.patch(loc_url, json={"monitoring_active": status}, headers=headers, timeout=5)
            return True
        except Exception as e:
            print(f"[!] Erro ao alterar status de monitoramento: {e}")
            return False

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Retorna uma lista de todos os usuários cadastrados."""
        url = f"{self.database_url}/users.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200 and res.json():
                users_dict = res.json()
                return list(users_dict.values())
        except Exception as e:
            print(f"[!] Erro ao buscar lista de usuários: {e}")
        return []

    def get_all_locations(self) -> Dict[str, Any]:
        """Retorna todas as localizações cadastradas."""
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
        """Garante que exista pelo menos o usuário admin inicial caso o DB esteja novo."""
        clean_user = "admin"
        url = f"{self.database_url}/users/{clean_user}.json"
        try:
            headers = self._get_headers()
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and not res.json():
                print("[*] Banco de dados inicializado. Criando conta administrador padrão: admin / admin123")
                self.create_user("admin", "admin123", "Administrador Geral", role="admin")
        except Exception:
            pass
