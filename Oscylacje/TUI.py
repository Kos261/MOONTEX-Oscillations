import time
import random
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel


def generate_table():
    """Funkcja tworząca tabelkę z aktualnymi danymi"""
    table = Table(title="Status Oscylatora", style="cyan")
    table.add_column("Parametr", style="magenta")
    table.add_column("Wartość", style="green")

    # Tu wstawiasz swoje prawdziwe zmienne
    predkosc = random.randint(100, 150)
    pozycja = random.uniform(0.0, 10.0)

    table.add_row("Prędkość (RPM)", f"{predkosc}")
    table.add_row("Pozycja (mm)", f"{pozycja:.2f}")
    table.add_row("Status", "[bold red]PRACA[/bold red]" if predkosc > 120 else "OK")

    return Panel(table, title="MOONTEX Control", border_style="blue")


# Główna pętla programu
if __name__ == "__main__":
    # refresh_per_second=4 odświeża ekran 4 razy na sekundę (żeby nie mrugało)
    with Live(generate_table(), refresh_per_second=10) as live:
        while True:
            # time.sleep(0.1)  # Symulacja pracy silnika
            live.update(generate_table())