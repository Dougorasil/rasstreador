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
from rich.text import Text

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
            mock_fallback=tracker_conf.get("mock_gps_fallback", True)
        )

        self.current_user = None
        self.tracking_active = False
        self.tracking_thread = None
        self.stop_tracking_event = threading.Event()
        self.last_captured_location = None

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
                "mock_gps_fallback": True
            }
        }

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def show_header(self):
        header_text = Text("RASTREADOR EM TEMPO REAL - TERMUX & FIREBASE", style="bold cyan")
        console.print(Panel(header_text, expand=False, border_style="cyan"))

    def login_screen(self):
        self.clear_screen()
        self.show_header()

        self.firebase.ensure_default_admin()

        console.print("[bold green]=== TELA DE LOGIN ===[/bold green]")
        username = Prompt.ask("[bold white]Usuário[/bold white]")
        password = Prompt.ask("[bold white]Senha[/bold white]", password=True)

        user_resp = self.firebase.login(username, password)

        if isinstance(user_resp, dict) and "error" in user_resp:
            console.print(f"\n[bold red][!] {user_resp['error']}[/bold red]")
            time.sleep(2.5)
            return False

        if isinstance(user_resp, dict) and "username" in user_resp:
            self.current_user = user_resp
            console.print(f"\n[bold green][✓] Login efetuado com sucesso! Bem-vindo(a), {user_resp.get('name', username)}[/bold green]")
            time.sleep(1.5)
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
                self.firebase.update_location(username, loc_data)

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
            console.print("[bold green][✓] Monitoramento ATIVADO! Obtendo sinal de GPS...[/bold green]")
            loc = self.tracker.capture_location()
            loc["username"] = username
            loc["name"] = self.current_user.get("name", username)
            loc["monitoring_active"] = True
            self.last_captured_location = loc
            self.firebase.update_location(username, loc)
        else:
            console.print("[bold yellow][!] Monitoramento DESATIVADO.[/bold yellow]")
            loc_data = self.last_captured_location or {}
            loc_data["monitoring_active"] = False
            loc_data["username"] = username
            self.firebase.update_location(username, loc_data)

        time.sleep(1.5)

    def display_current_location_panel(self):
        self.clear_screen()
        self.show_header()
        username = self.current_user.get("username")

        console.print("[bold green]=== LOCALIZAÇÃO EXATA EM TEMPO REAL ===[/bold green]\n")

        with console.status("[bold yellow]Capturando localização com alta precisão GPS/Rede...[/bold yellow]", spinner="dots"):
            loc = self.tracker.capture_location()
            loc["username"] = username
            loc["name"] = self.current_user.get("name", username)
            loc["monitoring_active"] = self.tracking_active
            self.last_captured_location = loc
            if self.tracking_active:
                self.firebase.update_location(username, loc)

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(style="bold cyan", justify="right")
        grid.add_column(style="bold white")

        grid.add_row("Status Monitoramento:", "[bold green]ATIVADO (5s)[/bold green]" if self.tracking_active else "[bold red]DESATIVADO[/bold red]")
        grid.add_row("Provedor de Sinal:", f"[yellow]{loc.get('provider', 'N/A').upper()}[/yellow] (Precisão: {loc.get('accuracy', 0):.1f}m)")
        grid.add_row("Rua / Número:", loc.get("street", "N/A"))
        grid.add_row("Bairro:", loc.get("neighborhood", "N/A"))
        grid.add_row("Cidade / Estado:", f"{loc.get('city', 'N/A')} - {loc.get('state', 'UF')}")
        if loc.get("postcode"):
            grid.add_row("CEP:", loc.get("postcode"))
        grid.add_row("Coordenadas Exatas:", f"{loc.get('latitude'):.7f}, {loc.get('longitude'):.7f}")
        grid.add_row("Link Direto Google Maps:", f"[link={loc.get('google_maps_url')}]{loc.get('google_maps_url')}[/link]")
        grid.add_row("Última Atualização:", loc.get("last_updated", "Agora"))

        panel = Panel(grid, title=f"Dispositivo de {self.current_user.get('name', username)}", border_style="green" if self.tracking_active else "red")
        console.print(panel)
        
        console.print("\n[dim]Pressione ENTER para voltar ao menu principal...[/dim]")
        input()

    def admin_panel_cli(self):
        while True:
            self.clear_screen()
            self.show_header()
            console.print("[bold magenta]=== PAINEL DO ADMINISTRADOR (CLI) ===[/bold magenta]\n")

            console.print("1. [cyan]Listar Todos os Usuários[/cyan]")
            console.print("2. [cyan]Ver Localização em Tempo Real de um Usuário[/cyan]")
            console.print("3. [cyan]Cadastrar Novo Usuário[/cyan]")
            console.print("4. [cyan]Ativar/Desativar Conta de Usuário[/cyan]")
            console.print("5. [bold yellow]Voltar ao Menu Principal[/bold yellow]\n")

            choice = Prompt.ask("Escolha uma opção", choices=["1", "2", "3", "4", "5"])

            if choice == "1":
                users = self.firebase.get_all_users()
                table = Table(title="Usuários Cadastrados no Sistema")
                table.add_column("Usuário", style="cyan")
                table.add_column("Nome", style="bold white")
                table.add_column("Função", style="magenta")
                table.add_column("Monitoramento", style="green")
                table.add_column("Conta Ativa", style="yellow")

                for u in users:
                    m_status = "[bold green]ATIVADO[/bold green]" if u.get("tracking_enabled") else "[red]DESATIVADO[/red]"
                    c_status = "[green]SIM[/green]" if u.get("active", True) else "[red]NÃO[/red]"
                    table.add_row(u.get("username"), u.get("name"), u.get("role"), m_status, c_status)

                console.print(table)
                input("\nPressione ENTER para continuar...")

            elif choice == "2":
                target_user = Prompt.ask("Digite o nome de usuário (username)").strip().lower()
                locations = self.firebase.get_all_locations()
                user_loc = locations.get(target_user)

                if user_loc:
                    table = Table(title=f"Localização Atual: {target_user}")
                    table.add_column("Campo", style="cyan")
                    table.add_column("Valor", style="white")
                    table.add_row("Provedor", user_loc.get("provider", "N/A"))
                    table.add_row("Rua", user_loc.get("street", "N/A"))
                    table.add_row("Bairro", user_loc.get("neighborhood", "N/A"))
                    table.add_row("Cidade", f"{user_loc.get('city')} - {user_loc.get('state')}")
                    table.add_row("Coordenadas", f"{user_loc.get('latitude')}, {user_loc.get('longitude')}")
                    table.add_row("Link Google Maps", user_loc.get("google_maps_url", "N/A"))
                    table.add_row("Última Atualização", user_loc.get("last_updated", "N/A"))
                    console.print(table)
                else:
                    console.print(f"[red]Nenhuma localização registrada para o usuário '{target_user}'.[/red]")
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
            
            console.print(f"Olá, [bold cyan]{name}[/bold cyan] | Função: [bold magenta]{role}[/bold magenta]")
            console.print(f"Status do Monitoramento: {status_str}\n")

            console.print("1. " + ("[bold red]DESATIVAR Monitoramento[/bold red]" if self.tracking_active else "[bold green]ATIVAR Monitoramento[/bold green]"))
            console.print("2. [cyan]Ver Minha Localização Exata (Rua, Bairro, Coordinates & Maps)[/cyan]")

            if self.current_user.get("role") == "admin":
                console.print("3. [bold magenta]Painel do Administrador (Gerenciar Usuários/Rastreios)[/bold magenta]")
                console.print("4. [bold yellow]Sair / Logout[/bold yellow]")
            else:
                console.print("3. [bold yellow]Sair / Logout[/bold yellow]")

            console.print("")

            choices = ["1", "2", "3", "4"] if self.current_user.get("role") == "admin" else ["1", "2", "3"]
            choice = Prompt.ask("Escolha uma opção", choices=choices)

            if choice == "1":
                self.toggle_tracking()
            elif choice == "2":
                self.display_current_location_panel()
            elif choice == "3" and self.current_user.get("role") == "admin":
                self.admin_panel_cli()
            elif choice == "3" and self.current_user.get("role") != "admin":
                self.logout()
                break
            elif choice == "4" and self.current_user.get("role") == "admin":
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
