import os
import sys
import time
import json
import subprocess

from firebase_service import FirebaseService
from tracker import LocationTracker

def run_daemon():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print("[!] config.json não encontrado.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    fb_conf = config.get("firebase", {})
    tracker_conf = config.get("tracker", {})
    daemon_conf = config.get("active_daemon_user", {})

    username = daemon_conf.get("username")
    name = daemon_conf.get("name", username)
    interval = tracker_conf.get("update_interval_seconds", 5)

    if not username:
        print("[!] Nenhum usuário logado para o serviço em segundo plano.")
        sys.exit(1)

    db_url = fb_conf.get("database_url", "")
    api_key = fb_conf.get("api_key", "")
    sa_file = fb_conf.get("service_account_file", "service_account.json")

    firebase = FirebaseService(db_url, api_key, service_account_file=sa_file)
    tracker = LocationTracker(
        use_termux_api=tracker_conf.get("use_termux_api", True),
        mock_fallback=tracker_conf.get("mock_gps_fallback", False)
    )

    # 1. Ativa Wake-Lock no Android para impedir o processador de dormir
    try:
        subprocess.run(["termux-wake-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # 2. Exibe Notificação de Primeiro Plano no Android
    try:
        subprocess.run([
            "termux-notification",
            "-t", "📍 Rastreamento GPS 24/7 Ativo",
            "-c", f"Dispositivo: {name} (Atualizando a cada 5s)",
            "--priority", "high"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    print(f"[*] Daemon de Rastreamento em Segundo Plano Iniciado para @{username}...")
    firebase.toggle_monitoring(username, True)

    try:
        while True:
            loc_data = tracker.capture_location()
            loc_data["username"] = username
            loc_data["name"] = name
            loc_data["monitoring_active"] = True

            firebase.update_location(username, loc_data)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[*] Daemon interrompido.")
        firebase.toggle_monitoring(username, False)
        try:
            subprocess.run(["termux-wake-unlock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["termux-notification-remove", "rastreador_gps_bg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

if __name__ == "__main__":
    run_daemon()
