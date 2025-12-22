#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import threading
import keyboard
from ticlib import TicUSB
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Console
from rich.align import Align
from dataclasses import dataclass

# ================= KONFIGURACJA (Skopiowana z oryginału) =================
X1_DEFAULT = -1100
X2_DEFAULT = 1100
CYCLES_DEFAULT = 10
DWELL_S = 0.3
TOLERANCE = 50
TIMEOUT_S = 60
KEEPALIVE_PERIOD = 0.05
MAX_SPEED = 60_000_000
MAX_ACCEL = 2_000_000
MAX_DECEL = 2 * MAX_ACCEL
START_SPEED = 0

@dataclass
class SharedState:
    position: int = 0
    velocity: int = 0
    voltage: float = 0.0
    current_limit: int = 0 #?
    cycle_goal: any = None
    cycle_current: int = 0
    status_msg: str = "Initializing"
    mode_name: str = "Waiting"
    error: str = ""
    running: bool = True

state = SharedState()


def safe_shutdown(tic):
    """Zatrzymuje silnik i odcina zasilanie"""
    if tic:
        try:
            tic.set_target_velocity(0)
            tic.enter_safe_start()
            tic.deenergize()
            print(f"Motor deenergized", file=sys.stderr)
        except Exception as e:
            pass
            print(f"[WARN] deenergize failed: {e}", file=sys.stderr)

def update_metrics(tic):
    try:
        state.position = tic.get_current_position()
        state.voltage = tic.get_vin_voltage() / 1000.0
    except Exception as e:
        state.error = str(e)

def wait_until_reached(tic, target, timeout_s, tolerance):
    """Keepalive prevents from turning off motor"""
    deadline = time.time() + timeout_s
    next_keepalive = 0.0
    while time.time() < deadline and state.running:
        now = time.time()
        if now >= next_keepalive:
            tic.reset_command_timeout()
            next_keepalive = now + KEEPALIVE_PERIOD

        update_metrics(tic)

        if abs(state.position - target) <= tolerance:
            return True

        if keyboard.is_pressed(" "):
            state.status_msg = "STOPPED (Space)"
            raise KeyboardInterrupt("Stopped by user")
        time.sleep(0.02)

    raise TimeoutError(f"Target {target} not reached (pos={state.position}).")


def move_and_wait(tic, target):
    state.status_msg = f"MOVING to {target}"
    tic.set_target_position(int(target))
    wait_until_reached(tic, int(target), timeout_s=TIMEOUT_S, tolerance=TOLERANCE)

def run_oscillations(tic, x1, x2, cycles_goal):
    state.mode_name = "OSCYLACJE"
    state.cycle_goal = cycles_goal
    state.cycle_current = 0

    # Wybór bliższego punktu
    cur = tic.get_current_position()
    first_target = x1 if abs(cur - x1) <= abs(cur - x2) else x2
    other_target = x2 if first_target == x1 else x1

    try:
        while state.running and (cycles_goal is None or state.cycle_current < cycles_goal):
            move_and_wait(tic, first_target)
            time.sleep(DWELL_S)
            move_and_wait(tic, other_target)
            time.sleep(DWELL_S)
            move_and_wait(tic, first_target)

            state.cycle_current += 1

        state.status_msg = "Zakończono cykle. Powrót do 0."
        time.sleep(DWELL_S)
        move_and_wait(tic, 0)
        state.status_msg = "Gotowe."

    except KeyboardInterrupt:
        state.status_msg = "Przerwano ręcznie!"
        tic.set_target_velocity(0)


def run_manual(tic):
    state.mode_name = "MANUAL (WASD)"
    state.status_msg = "Use keys WASD. Space=STOP. Q=Exit"

    speed = max(1, int(MAX_SPEED * 0.33))
    accel = max(1, int(MAX_ACCEL * 0.8))
    decel = max(1, int(MAX_DECEL * 0.8))

    tic.set_max_acceleration(accel)
    tic.set_max_deceleration(decel)
    tic.set_max_speed(speed)

    last_update = 0

    while state.running:
        now = time.time()
        if now - last_update > 0.1:
            update_metrics(tic)
            last_update = now
            state.velocity = speed  # Aktualizacja wyświetlania zadanej prędkości

        # Sterowanie
        if keyboard.is_pressed("a"):
            tic.set_target_velocity(-speed)
            state.status_msg = "<< GOING LEFT"
        elif keyboard.is_pressed("d"):
            tic.set_target_velocity(speed)
            state.status_msg = "GOING RIGHT >>"
        else:
            tic.set_target_velocity(0)
            state.status_msg = "HOLD A OR D TO MOVE"

        # Zmiana prędkości
        if keyboard.is_pressed("up"):
            speed = min(MAX_SPEED, int(speed * 1.1) + 100)
            tic.set_max_speed(speed)
            time.sleep(0.1)
        if keyboard.is_pressed("down"):
            speed = max(1000, int(speed / 1.1))
            tic.set_max_speed(speed)
            time.sleep(0.1)

        if keyboard.is_pressed("space"):
            tic.set_target_velocity(0)
            state.status_msg = "STOPPED"
            time.sleep(0.5)

        if keyboard.is_pressed("q"):
            state.status_msg = "EXITING MANUAL MODE"
            break

        tic.reset_command_timeout()
        time.sleep(0.01)


def run_constant_speed(tic, speed, cycles_goal):
    state.mode_name = "CONSTANT SPEED"
    state.cycle_goal = cycles_goal
    steps_per_rev = 400 * 18

    tic.set_target_velocity(speed)
    prev_pos_mod = tic.get_current_position() % steps_per_rev

    try:
        while state.running and state.cycle_current < cycles_goal:
            update_metrics(tic)
            cur = state.position
            pos_mod = cur % steps_per_rev

            # Detekcja obrotu
            if pos_mod < prev_pos_mod:
                state.cycle_current += 1
            prev_pos_mod = pos_mod

            tic.reset_command_timeout()

            if keyboard.is_pressed(" "):
                raise KeyboardInterrupt

            state.status_msg = f"CYCLES {speed} crocs/s"
            time.sleep(0.02)

    except KeyboardInterrupt:
        state.status_msg = "STOPPED"
        tic.set_target_velocity(0)


def motor_thread_func(choice, params):
    try:
        state.status_msg = "Łączenie z TicUSB..."
        tic = TicUSB()
        tic.energize()
        tic.exit_safe_start()
        tic.halt_and_set_position(0)
        # SET MAX VALUES
        state.current_limit = tic.settings.get_current_limit()
        tic.set_starting_speed(START_SPEED)
        tic.set_max_speed(MAX_SPEED)
        tic.set_max_acceleration(int(MAX_ACCEL * 0.7))
        tic.set_max_deceleration(int(MAX_DECEL * 0.7))

        if choice == 1:
            run_oscillations(tic, params['x1'], params['x2'], params['cycles'])
        elif choice == 2:
            run_constant_speed(tic, int(MAX_SPEED * 0.6), params['cycles'])
        elif choice == 3:
            run_manual(tic)

    except Exception as e:
        state.error = str(e)
        state.status_msg = "ERROR"
    finally:
        safe_shutdown(tic)
        state.running = False

def make_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    return layout

def generate_dashboard():
    # 1. Tabela Statusu (Lewa strona)
    status_table = Table(title="Parametry Silnika", expand=True, border_style="blue")
    status_table.add_column("Parametr", style="cyan")
    status_table.add_column("Wartość", justify="right", style="green")

    status_table.add_row("Tryb", f"[bold yellow]{state.mode_name}[/]")
    status_table.add_row("Pozycja", f"{state.position} µstep")
    status_table.add_row("Napięcie (VIN)", f"{state.voltage:.2f} V")

    # Koloruj napięcie na czerwono jeśli niebezpieczne
    volt_style = "red blink" if state.voltage > 28.0 else "green"
    status_table.rows[2].style = volt_style

    status_table.add_row("Limit Prądu", f"{state.current_limit} mA")

    if state.cycle_goal:
        prog = f"{state.cycle_current} / {state.cycle_goal}"
    else:
        prog = f"{state.cycle_current}"
    status_table.add_row("Licznik Cykli", prog)

    # 2. Panel Info (Prawa strona) - Zależny od trybu
    if "MANUAL" in state.mode_name:
        info_text = Text.from_markup("""
[bold underline]STEROWANIE:[/bold underline]
[bold green]A / D[/]     - Ruch Lewo/Prawo
[bold green]W / S[/]     - Prędkość +/-
[bold yellow]Q[/]         - Zakończ
[bold red]SPACJA[/]    - STOP AWARYJNY
""")
    else:
        info_text = Text.from_markup("""
[bold underline]STATUS AUTOMATYCZNY:[/bold underline]
Program wykonuje zadaną sekwencję.

[bold red]SPACJA[/] - Zatrzymaj program
""")

    if state.error:
        right_panel = Panel(Text(f"BŁĄD: {state.error}", style="bold white on red"), title="Alert",
                            border_style="red")
    else:
        right_panel = Panel(Align.center(info_text, vertical="middle"), title="Instrukcja", border_style="white")

    # 3. Footer (Komunikaty)
    msg_color = "red" if "ZATRZYMANO" in state.status_msg or "BŁĄD" in state.status_msg else "white"
    footer_panel = Panel(Text(state.status_msg, style=f"bold {msg_color}"), title="Log Systemowy")

    # Złożenie całości
    layout = make_layout()
    layout["header"].update(Panel(Align.center("[bold magenta]MOONTEX MOTOR CONTROLLER v2.0[/]"), style="blue"))
    layout["left"].update(Panel(status_table, title="Dane Live"))
    layout["right"].update(right_panel)
    layout["footer"].update(footer_panel)

    return layout


def main():
    console = Console()
    console.clear()
    console.print("[bold cyan]Wybierz tryb pracy:[/]")
    console.print("1. Oscylacje (x1 <-> x2)")
    console.print("2. Stała prędkość")
    console.print("3. Manualny (Klawiatura)")

    try:
        choice = int(input("Twój wybór (1-3): ").strip())
    except:
        choice = 3

    params = {}
    if choice == 1:
        try:
            c_in = input(f"Liczba cykli [enter={CYCLES_DEFAULT}]: ")
            params['cycles'] = int(c_in) if c_in else CYCLES_DEFAULT
            params['x1'] = X1_DEFAULT
            params['x2'] = X2_DEFAULT
        except:
            params['cycles'] = CYCLES_DEFAULT

    elif choice == 2:
        params['cycles'] = 1000  # Default huge

    # Uruchomienie wątku silnika
    motor_thread = threading.Thread(target=motor_thread_func, args=(choice, params), daemon=True)
    motor_thread.start()

    # Uruchomienie TUI
    try:
        with Live(generate_dashboard(), refresh_per_second=10, screen=True) as live:
            while state.running and motor_thread.is_alive():
                live.update(generate_dashboard())
                time.sleep(0.1)
    except KeyboardInterrupt:
        state.running = False

    # Czekaj na zakończenie wątku silnika
    state.running = False
    motor_thread.join(timeout=2.0)
    print("Program zakończony.")

if __name__ == "__main__":
    main()