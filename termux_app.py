import os
import sys
import time
import json
import threading
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns
from rich.align import Align

from firebase_service import FirebaseService
from tracker import LocationTracker

console = Console()

class TermuxTrackerApp:
    def __init__(self):
        self.config = self.load_config()
        fb_conf = self.config.get("firebase", {})
        tracker_conf = self.config.get("tracker", {})

        self.db_url = fb_conf.get("database_url", "")
        self.api_key = fb_conf.get("api_key", "")
        self.sa_file = fb_conf.get("service_account_file", "service_account.json")
        self.update_interval = tracker_conf.get("update_interval_seconds", 5)

        self.firebase = FirebaseService(self.db_url, self.api_key, service_account_file=self.sa_file)
        self.tracker = LocationTracker(
            use_termux_api=tracker_conf.get("use_termux_api", True),
            mock_fallback=tracker_conf.get("mock_gps_fallback", False)
        )

        self.current_user = None
        self.tracking_active = False
        self.tracking_thread = None
        self.stop_tracking_event = threading.Event()
        self.last_captured_location = None
        self.logs_history = []

    def load_config(self) -> dict:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[bold red][!] Erro ao carregar config.json: {e}[/bold red]")
        
        return {
            "firebase": {
                "database_url": "https://rastreador-c229f-default-rtdb.firebaseio.com",
                "service_account_file": "service_account.json"
            },
            "tracker": {
                "update_interval_seconds": 5,
                "use_termux_api": True,
                "mock_gps_fallback": False
            }
        }

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def show_header(self):
        header_text = Text("🛰️ RASTREADOR GPS HARDWARE - TERMUX & FIREBASE ⚡", style="bold cyan")
        sub_header = Text("Monitoramento em Tempo Real • Alta Precisão a cada 5s", style="dim white")
        content = Text.assemble(header_text, "\n", sub_header)
        console.print(Panel(Align.center(content), expand=True, border_style="cyan"))

    def add_log(self, msg: str):
        now = time.strftime("%H:%M:%S")
        self.logs_history.append(f"[{now}] {msg}")
        if len(self.logs_history) > 6:
            self.logs_history.pop(0)

    def login_screen(self):
        self.clear_screen()
        self.show_header()

        self.firebase.ensure_default_admin()

        console.print("[bold green]=== TELA DE AUTENTICAÇÃO ===[/bold green]\n")
        username = Prompt.ask("[bold white]Usuário[/bold white]")
        password = Prompt.ask("[bold white]Senha[/bold white]", password=True)

        with console.status("[bold yellow]Autenticando no Firebase...[/bold yellow]"):
            user_resp = self.firebase.login(username, password)

        if isinstance(user_resp, dict) and "error" in user_resp:
            console.print(f"\n[bold red][!] {user_resp['error']}[/bold red]")
            time.sleep(2.5)
            return False

        if isinstance(user_resp, dict) and "username" in user_resp:
            self.current_user = user_resp
            console.print(f"\n[bold green][✓] Login efetuado com sucesso! Bem-vindo(a), {user_resp.get('name', username)}[/bold green]")
            time.sleep(1.2)
            return True
        else:
            console.print("\n[bold red][!] Falha ao realizar login.[/bold red]")
            time.sleep(2)
            return False

    def tracking_worker(self):
        username = self.current_user.get("username")
        name = self.current_user.get("name", username)

        while not self.stop_tracking_event.is_set():
            if self.tracking_active:
                loc_data = self.tracker.capture_location()
                loc_data["username"] = username
                loc_data["name"] = name
                loc_data["monitoring_active"] = True

                self.last_captured_location = loc_data
                ok = self.firebase.update_location(username, loc_data)
                
                prov = loc_data.get("provider", "gps").upper()
                acc = loc_data.get("accuracy", 0.0)
                if ok:
                    self.add_log(f"🟢 GPS {prov} ({acc:.1f}m) -> Firebase OK")
                else:
                    self.add_log("🔴 Erro ao sincronizar com Firebase")

            for _ in range(self.update_interval * 2):
                if self.stop_tracking_event.is_set():
                    break
                time.sleep(0.5)

    def start_background_tracker(self):
        if self.tracking_thread is None or not self.tracking_thread.is_alive():
            self.stop_tracking_event.clear()
            self.tracking_thread = threading.Thread(target=self.tracking_worker, daemon=True)
            self.tracking_thread.start()

    def toggle_tracking(self):
        username = self.current_user.get("username")
        new_status = not self.tracking_active
        self.tracking_active = new_status
        self.firebase.toggle_monitoring(username, new_status)

        if new_status:
            console.print("\n[bold green][✓] Rastreamento GPS ATIVADO! Lendo hardware do celular...[/bold green]")
            loc = self.tracker.capture_location()
            loc["username"] = username
            loc["name"] = self.current_user.get("name", username)
            loc["monitoring_active"] = True
            self.last_captured_location = loc
            self.firebase.update_location(username, loc)
            self.add_log("Monitoramento GPS ativado")
        else:
            console.print("\n[bold yellow][!] Rastreamento GPS DESATIVADO.[/bold yellow]")
            loc_data = self.last_captured_location or {}
            loc_data["monitoring_active"] = False
            loc_data["username"] = username
            self.firebase.update_location(username, loc_data)
            self.add_log("Monitoramento GPS desativado")

        time.sleep(1.5)

    def display_current_location_panel(self):
        self.clear_screen()
        self.show_header()
        username = self.current_user.get("username")

        console.print("[bold green]=== MONITORAMENTO GPS DE ALTA PRECISÃO ===[/bold green]\n")

        with console.status("[bold yellow]Lendo satélites de GPS do celular...[/bold yellow]", spinner="dots"):
            loc = self.tracker.capture_location()
            loc["username"] = username
            loc["name"] = self.current_user.get("name", username)
            loc["monitoring_active"] = self.tracking_active
            self.last_captured_location = loc
            if self.tracking_active:
                self.firebase.update_location(username, loc)

        lat = loc.get("latitude", 0.0)
        lng = loc.get("longitude", 0.0)
        prov = loc.get("provider", "N/A").upper()
        acc = loc.get("accuracy", 0.0)
        speed = loc.get("speed", 0.0) * 3.6  # Converte m/s para km/h
        alt = loc.get("altitude", 0.0)

        # Status badge
        if "GPS" in prov:
            status_badge = "[bold green]🟢 FIX SATÉLITE GPS REAL[/bold green]"
        elif "NETWORK" in prov:
            status_badge = "[bold yellow]🟡 REDE CELULAR/WI-FI[/bold yellow]"
        else:
            status_badge = "[bold red]🔴 AGUARDANDO SINAL GPS[/bold red]"

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(style="bold cyan", justify="right")
        grid.add_column(style="bold white")

        grid.add_row("Status do GPS:", status_badge)
        grid.add_row("Provedor / Precisão:", f"[bold green]{prov}[/bold green] | Precisão: [bold yellow]{acc:.1f} metros[/bold yellow]")
        grid.add_row("Velocidade / Altitude:", f"[white]{speed:.1f} km/h[/white] | Altitude: [white]{alt:.1f} m[/white]")
        grid.add_row("Rua / Número:", loc.get("street", "N/A"))
        grid.add_row("Bairro:", loc.get("neighborhood", "N/A"))
        grid.add_row("Cidade / Estado:", f"{loc.get('city', 'N/A')} - {loc.get('state', 'UF')}")
        if loc.get("postcode"):
            grid.add_row("CEP:", loc.get("postcode"))
        grid.add_row("Coordenadas Exatas:", f"[bold white]{lat:.7f}, {lng:.7f}[/bold white]")
        if loc.get("google_maps_url"):
            grid.add_row("Link Google Maps:", f"[link={loc.get('google_maps_url')}][bold yellow]{loc.get('google_maps_url')}[/bold yellow][/link]")
        grid.add_row("Última Leitura:", loc.get("last_updated", "Agora"))

        panel = Panel(grid, title=f"Telemetria do Dispositivo - {self.current_user.get('name', username)}", border_style="green" if self.tracking_active else "red")
        console.print(panel)

        if self.logs_history:
            log_text = "\n".join(self.logs_history)
            console.print(Panel(log_text, title="📜 Histórico de Sincronizações (5s)", border_style="dim white"))
        
        console.print("\n[dim]Pressione ENTER para retornar ao menu principal...[/dim]")
        input()

    def run_gps_diagnostic(self):
        self.clear_screen()
        self.show_header()
        console.print("[bold yellow]=== DIAGNÓSTICO DO HARDWARE GPS DO CELULAR ===[/bold yellow]\n")
        console.print("[white]Iniciando teste direto do receptor de GPS (termux-location)...[/white]\n")

        with console.status("[bold green]Procurando satélites GPS ativos...[/bold green]", spinner="earth"):
            start_t = time.time()
            gps_data = self.tracker.get_raw_gps()
            elapsed = time.time() - start_t

        table = Table(title="Resultado do Teste de Diagnóstico GPS")
        table.add_column("Parâmetro", style="cyan")
        table.add_column("Resultado", style="white")

        table.add_row("Tempo de Resposta", f"{elapsed:.2f} segundos")
        table.add_row("Status do Sinal", gps_data.get("status", "N/A").upper())
        table.add_row("Provedor Detectado", gps_data.get("provider", "N/A").upper())
        table.add_row("Latitude / Longitude", f"{gps_data.get('latitude'):.7f}, {gps_data.get('longitude'):.7f}")
        table.add_row("Precisão (Erro de Raio)", f"{gps_data.get('accuracy', 0.0):.1f} metros")
        table.add_row("Altitude", f"{gps_data.get('altitude', 0.0):.1f} metros")
        table.add_row("Velocidade Atual", f"{gps_data.get('speed', 0.0) * 3.6:.1f} km/h")

        console.print(table)
        console.print("\n[dim]Pressione ENTER para voltar ao menu...[/dim]")
        input()

    def admin_panel_cli(self):
        while True:
            self.clear_screen()
            self.show_header()
            console.print("[bold magenta]=== PAINEL DO ADMINISTRADOR (CLI) ===[/bold magenta]\n")

            console.print("1. [cyan]Listar Todos os Dispositivos & Status[/cyan]")
            console.print("2. [cyan]Ver Localização Exata & Telemetria de um Usuário[/cyan]")
            console.print("3. [cyan]Cadastrar Novo Usuário (Termux / Web)[/cyan]")
            console.print("4. [cyan]Ativar/Desativar Conta de Usuário[/cyan]")
            console.print("5. [bold yellow]Voltar ao Menu Principal[/bold yellow]\n")

            choice = Prompt.ask("Escolha uma opção", choices=["1", "2", "3", "4", "5"])

            if choice == "1":
                users = self.firebase.get_all_users()
                locations = self.firebase.get_all_locations()

                table = Table(title="Lista de Dispositivos e Usuários Registrados")
                table.add_column("Usuário", style="cyan")
                table.add_column("Nome", style="bold white")
                table.add_column("Função", style="magenta")
                table.add_column("Monitorando (5s)", style="green")
                table.add_column("Último Endereço", style="yellow")

                for u in users:
                    u_name = u.get("username")
                    m_status = "[bold green]ON (5s)[/bold green]" if u.get("tracking_enabled") else "[red]OFF[/red]"
                    user_loc = locations.get(u_name, {})
                    street_info = user_loc.get("street", "Sem registro")

                    table.add_row(u_name, u.get("name"), u.get("role"), m_status, street_info)

                console.print(table)
                input("\nPressione ENTER para continuar...")

            elif choice == "2":
                target_user = Prompt.ask("Digite o nome de usuário (username)").strip().lower()
                locations = self.firebase.get_all_locations()
                user_loc = locations.get(target_user)

                if user_loc:
                    table = Table(title=f"Telemetria em Tempo Real: {target_user}")
                    table.add_column("Campo", style="cyan")
                    table.add_column("Valor", style="white")
                    table.add_row("Status", "🟢 Ativo" if user_loc.get("monitoring_active") else "🔴 Inativo")
                    table.add_row("Provedor", user_loc.get("provider", "N/A"))
                    table.add_row("Rua / Número", user_loc.get("street", "N/A"))
                    table.add_row("Bairro", user_loc.get("neighborhood", "N/A"))
                    table.add_row("Cidade", f"{user_loc.get('city')} - {user_loc.get('state')}")
                    table.add_row("Coordenadas", f"{user_loc.get('latitude')}, {user_loc.get('longitude')}")
                    table.add_row("Link Google Maps", user_loc.get("google_maps_url", "N/A"))
                    table.add_row("Última Atualização", user_loc.get("last_updated", "N/A"))
                    console.print(table)
                else:
                    console.print(f"[red]Nenhuma localização registrada para '{target_user}'.[/red]")
                input("\nPressione ENTER para continuar...")

            elif choice == "3":
                console.print("\n[bold green]--- Cadastrar Novo Usuário ---[/bold green]")
                new_user = Prompt.ask("Novo Username").strip().lower()
                new_name = Prompt.ask("Nome Completo")
                new_pass = Prompt.ask("Senha", password=True)
                new_role = Prompt.ask("Função (user/admin)", choices=["user", "admin"], default="user")

                if self.firebase.create_user(new_user, new_pass, new_name, new_role):
                    console.print(f"[bold green][✓] Usuário '{new_user}' cadastrado com sucesso![/bold green]")
                else:
                    console.print("[bold red][!] Falha ao cadastrar usuário.[/bold red]")
                time.sleep(2)

            elif choice == "4":
                target_user = Prompt.ask("Username para alterar").strip().lower()
                users = self.firebase.get_all_users()
                u_data = next((u for u in users if u.get("username") == target_user), None)
                if u_data:
                    current_active = u_data.get("active", True)
                    new_active = not current_active
                    url = f"{self.firebase.database_url}/users/{target_user}.json"
                    headers = self.firebase._get_headers()
                    import requests
                    requests.patch(url, json={"active": new_active}, headers=headers)
                    console.print(f"[bold green][✓] Conta '{target_user}' {'ativada' if new_active else 'desativada'} com sucesso![/bold green]")
                else:
                    console.print("[red]Usuário não encontrado.[/red]")
                time.sleep(2)

            elif choice == "5":
                break

    def main_menu(self):
        self.start_background_tracker()

        while True:
            self.clear_screen()
            self.show_header()

            name = self.current_user.get("name", self.current_user.get("username"))
            role = self.current_user.get("role", "user").upper()

            status_str = "[bold green]ATIVADO (Atualizando a cada 5s)[/bold green]" if self.tracking_active else "[bold red]DESATIVADO[/bold red]"
            
            console.print(f"Dispositivo: [bold cyan]{name}[/bold cyan] | Função: [bold magenta]{role}[/bold magenta]")
            console.print(f"Status do GPS Hardware: {status_str}\n")

            console.print("1. " + ("[bold red]DESATIVAR Monitoramento GPS[/bold red]" if self.tracking_active else "[bold green]ATIVAR Monitoramento GPS[/bold green]"))
            console.print("2. [cyan]Ver Minha Localização Exata & Telemetria[/cyan]")
            console.print("3. [yellow]Executar Teste de Diagnóstico do Receptor GPS[/yellow]")

            if self.current_user.get("role") == "admin":
                console.print("4. [bold magenta]Painel do Administrador (Gerenciar Usuários)[/bold magenta]")
                console.print("5. [bold red]Sair / Logout[/bold red]")
            else:
                console.print("4. [bold red]Sair / Logout[/bold red]")

            console.print("")

            choices = ["1", "2", "3", "4", "5"] if self.current_user.get("role") == "admin" else ["1", "2", "3", "4"]
            choice = Prompt.ask("Escolha uma opção", choices=choices)

            if choice == "1":
                self.toggle_tracking()
            elif choice == "2":
                self.display_current_location_panel()
            elif choice == "3":
                self.run_gps_diagnostic()
            elif choice == "4" and self.current_user.get("role") == "admin":
                self.admin_panel_cli()
            elif choice == "4" and self.current_user.get("role") != "admin":
                self.logout()
                break
            elif choice == "5" and self.current_user.get("role") == "admin":
                self.logout()
                break

    def logout(self):
        self.tracking_active = False
        self.stop_tracking_event.set()
        if self.current_user:
            username = self.current_user.get("username")
            self.firebase.toggle_monitoring(username, False)
        self.current_user = None
        console.print("[yellow]Sessão encerrada.[/yellow]")
        time.sleep(1)

    def run(self):
        while True:
            if not self.login_screen():
                if not Confirm.ask("Deseja tentar fazer login novamente?", default=True):
                    console.print("[bold cyan]Encerrando aplicativo. Até logo![/bold cyan]")
                    break
            else:
                self.main_menu()

if __name__ == "__main__":
    app = TermuxTrackerApp()
    try:
        app.run()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Aplicação interrompida pelo usuário.[/bold yellow]")
        sys.exit(0)
