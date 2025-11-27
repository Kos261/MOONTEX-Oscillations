#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import keyboard
from ticlib import TicUSB

# -------- DOMYŚLNA KONFIGURACJA (można nadpisać z CLI / interaktywnie) --------
X1_DEFAULT = -1100                   # punkt krańcowy 1 (µkroki)
X2_DEFAULT =  1100                   # punkt krańcowy 2 (µkroki)
CYCLES_DEFAULT = 10                  # liczba pełnych cykli (x1->x2->x1 lub x2->x1->x2); None = bez limitu

DWELL_S = 0.3                        # pauza na krańcu
TOLERANCE = 50                       # akceptowalny błąd pozycji [µkroki]
TIMEOUT_S = 60                       # maks. oczekiwanie na dojazd jednego odcinka
KEEPALIVE_PERIOD = 0.05              # reset command timeout co ...

# Limity ruchu — **ustaw realistycznie** dla swojego układu
SET_LIMITS = True
MAX_SPEED = 60_000_000
MAX_ACCEL = 2_000_000
MAX_DECEL = 2*MAX_ACCEL
START_SPEED = 0
# ------------------------------------------------------------------------------

def _prompt_int(prompt, default=None, allow_none=False):
    """
    Pyta użytkownika o liczbę całkowitą.
    - Enter przyjmuje default (jeśli podany).
    - Jeśli allow_none=True, wpisanie 'inf', '∞', 'none', '' (przy braku domyślnej)
      zwraca None (np. nielimitowane cykle).
    """
    while True:
        txt = input(prompt).strip()

        # puste wejście
        if txt == "":
            if default is not None:
                return int(default)
            if allow_none:
                return None
            print("Wpisz liczbę całkowitą.")
            continue

        # symbole nieskończoności dla allow_none
        if allow_none and txt.lower() in ("inf", "∞", "none", "bez", "nolimit", "nieskonczonosc"):
            return None

        try:
            return int(txt)
        except ValueError:
            print("Nieprawidłowa wartość. Wpisz liczbę całkowitą (np. 10, -1100, 1100).")

def parse_interactive():
    """
    Tryb interaktywny — pyta o cycles (może być None), x1, x2.
    Enter = domyślne. Dla cycles można wpisać 'inf' / '∞' / zostawić puste (bez limitu).
    """
    print("\n=== USTAWIENIA OSCYLACJI (tryb interaktywny) ===")
    print("Podaj parametry. Wciśnij Enter, aby użyć wartości domyślnych.\n")

    # Cykle: dopuszczamy nieskończoność (None)
    cycles_prompt = f"Liczba pełnych cykli [enter=domyślnie {CYCLES_DEFAULT}, 'inf'=bez limitu]: "
    cycles = _prompt_int(cycles_prompt, default=CYCLES_DEFAULT, allow_none=True)

    x1 = _prompt_int(f"Punkt krańcowy x1 (µkroki) [enter={X1_DEFAULT}]: ", default=X1_DEFAULT)
    x2 = _prompt_int(f"Punkt krańcowy x2 (µkroki) [enter={X2_DEFAULT}]: ", default=X2_DEFAULT)

    if x1 == x2:
        print("x1 i x2 nie mogą być równe — spróbuj ponownie.\n")
        return parse_interactive()

    return x1, x2, cycles

def parse_cli_or_interactive():
    """
    Jeśli podano argumenty CLI: [cycles] [x1] [x2] — użyj ich.
    W przeciwnym razie przejdź w tryb interaktywny i zapytaj użytkownika.
    """
    if len(sys.argv) >= 2:
        # tryb CLI jak poprzednio
        cycles, x1, x2 = CYCLES_DEFAULT, X1_DEFAULT, X2_DEFAULT
        try:
            if len(sys.argv) >= 2: cycles = int(sys.argv[1]) if sys.argv[1].lower() not in ("inf", "∞", "none") else None
            if len(sys.argv) >= 3: x1 = int(sys.argv[2])
            if len(sys.argv) >= 4: x2 = int(sys.argv[3])
        except ValueError:
            print("Uwaga: błędny argument CLI — przechodzę do trybu interaktywnego.")
            return parse_interactive()
        if x1 == x2:
            raise ValueError("x1 i x2 nie mogą być równe.")
        return x1, x2, cycles
    else:
        # tryb interaktywny
        return parse_interactive()

def wait_until_reached(tic, target, timeout_s, tolerance):
    """Czeka aż silnik znajdzie się w pobliżu celu (z podtrzymaniem timeoutu)."""
    deadline = time.time() + timeout_s
    next_keepalive = 0.0
    while time.time() < deadline:
        now = time.time()
        if now >= next_keepalive:
            tic.reset_command_timeout()
            next_keepalive = now + KEEPALIVE_PERIOD

        cur = tic.get_current_position()
        if abs(cur - target) <= tolerance:
            return True
        time.sleep(0.02)

    cur = tic.get_current_position()
    raise TimeoutError(f"Nie osiągnięto pozycji {target} w {timeout_s}s (cur={cur}).")

def move_and_wait(tic, target):
    tic.set_target_position(int(target))
    return wait_until_reached(tic, int(target), TIMEOUT_S, TOLERANCE)

def oscillations(tic, x1,x2, cycles_goal):
    cur = tic.get_current_position()
    # Wybierz bliższy punkt na start
    first_target = x1 if abs(cur - x1) <= abs(cur - x2) else x2
    other_target = x2 if first_target == x1 else x1

    cycles_txt = "bez limitu" if cycles_goal is None else str(cycles_goal)
    print(f"\nStart. Pozycja bieżąca: {cur} µkroków. x1={x1}, x2={x2}, cycles={cycles_txt}")
    print(f"Pierwszy cel: {first_target}\n")

    cycles_done = 0
    while cycles_goal is None or cycles_done < cycles_goal:
        move_and_wait(tic, first_target)
        time.sleep(DWELL_S)
        move_and_wait(tic, other_target)
        time.sleep(DWELL_S)
        move_and_wait(tic, first_target)
        cycles_done += 1
    time.sleep(DWELL_S)
    move_and_wait(tic, 0)

def keep_moving(tic, speed=int(MAX_SPEED * 0.33), cycles_goal=10):
    counter = 0
    accel = max(1, int(MAX_ACCEL * 0.8))
    decel = max(1, int(MAX_DECEL * 0.8))

    tic.set_max_acceleration(accel)
    tic.set_max_deceleration(decel)
    tic.set_max_speed(speed)

    steps_per_rev = 400 * 18
    prev_pos_mod = tic.get_current_position() % steps_per_rev

    try:
        while counter < cycles_goal:
            cur = tic.get_current_position()
            pos_mod = cur % steps_per_rev

            # if positive direction
            if pos_mod < prev_pos_mod:
                counter += 1
                print("Cycle:", counter)

            prev_pos_mod = pos_mod

            tic.set_target_velocity(speed)
            if keyboard.is_pressed(" "):
                tic.set_target_velocity(0)
                return

            tic.reset_command_timeout()
    except KeyboardInterrupt:
        print("\n[MAN] Przerwano przez użytkownika.")

def manual_move(tic):
    """
    Sterowanie ręczne z klawiatury (prędkość ciągła).
    Użyj klawiszy podanych w _print_manual_help().
    """
    # startowe parametry
    speed = max(1, int(MAX_SPEED * 0.33))
    accel = max(1, int(MAX_ACCEL * 0.8))
    decel = max(1, int(MAX_DECEL * 0.8))

    tic.set_max_acceleration(accel)
    tic.set_max_deceleration(decel)
    tic.set_max_speed(speed)

    print("\n[MAN] Sterowanie ręczne uruchomione. Naciśnij 'h' aby wyświetlić pomoc.")
    last_print = 0.0
    try:
        while True:
            # kierunek
            if keyboard.is_pressed("a"):
                tic.set_target_velocity(-speed)
            elif keyboard.is_pressed("d"):
                tic.set_target_velocity(speed)
            else:
                tic.set_target_velocity(0)

            # zmiany parametrów
            bumped = False
            if keyboard.is_pressed("up"):
                speed = min(MAX_SPEED, int(speed * 1.2) + 1); bumped = True
                tic.set_max_speed(speed)
                time.sleep(0.08)
            if keyboard.is_pressed("down"):
                speed = max(1000, int(speed / 1.2)); bumped = True
                tic.set_max_speed(speed)
                time.sleep(0.08)
            if keyboard.is_pressed("right"):
                accel = min(MAX_ACCEL, int(accel * 1.2) + 1)
                decel = min(MAX_DECEL, int(decel * 1.2) + 1); bumped = True
                tic.set_max_acceleration(accel); tic.set_max_deceleration(decel)
                time.sleep(0.08)
            if keyboard.is_pressed("left"):
                accel = max(1000, int(accel / 1.2))
                decel = max(1000, int(decel / 1.2)); bumped = True
                tic.set_max_acceleration(accel); tic.set_max_deceleration(decel)
                time.sleep(0.08)

            # akcje narzędziowe
            if keyboard.is_pressed(" "):  # spacja: STOP
                tic.set_target_velocity(0)
                print("[MAN] STOP")
                time.sleep(0.15)
            if keyboard.is_pressed("z"):  # 'z': wyzeruj licznik pozycji
                tic.halt_and_set_position(0)
                print("[MAN] Ustawiono bieżącą pozycję = 0")
                time.sleep(0.15)
            if keyboard.is_pressed("0"):  # '0': jedź do zera
                print("[MAN] Jadę do 0...")
                move_and_wait(tic, 0)
                time.sleep(0.15)
            if keyboard.is_pressed("q"):
                print("[MAN] Zakończono sterowanie ręczne.")
                break

            tic.reset_command_timeout()

            # ogranicz spam w konsoli
            now = time.time()
            if now - last_print > 0.25 or bumped:
                try:
                    pos = tic.get_current_position()
                except Exception:
                    pos = "?"
                print(f"[MAN] pos={pos}  speed={speed}  acc={accel}  dec={decel}", end="\r")
                last_print = now

    except KeyboardInterrupt:
        print("\n[MAN] Przerwano przez użytkownika.")

def init_and_configure():
    tic = TicUSB()
    tic.energize()
    tic.exit_safe_start()
    tic.halt_and_set_position(0)  # start od 0

    if SET_LIMITS:
        tic.set_starting_speed(START_SPEED)
        tic.set_max_speed(MAX_SPEED)
        tic.set_max_acceleration(int(MAX_ACCEL * 0.8))  # delikatniej
        tic.set_max_deceleration(int(MAX_DECEL * 0.8))
    return tic

def main():
    # 1. wybór trybu
    while True:
        try:
            choice = int(input("Chose Oscillations (1) or Constant speed (2): "))
        except ValueError:
            print("Podaj 1 lub 2.")
            continue

        if choice in (1, 2):
            break
        else:
            print("Podaj 1 lub 2.")

    if choice == 1:
        x1, x2, cycles_goal = parse_cli_or_interactive()
        speed = None  # Na razie bez  speed ale można dodać
    else:
        while True:
            try:
                cycles_goal = int(input("Cycles goal: "))
            except ValueError:
                print("Podaj liczbę całkowitą.")
                continue
            if cycles_goal > 0:
                break
            else:
                print("Liczba cykli musi być dodatnia.")

        # możesz też zrobić input na speed, ale zostawiam Twoje stałe 0.6
        speed = int(MAX_SPEED * 0.6)

    # 3. dopiero teraz konfigurujesz Tic + ruch
    tic = init_and_configure()

    try:
        if choice == 1:
            oscillations(tic, x1, x2, cycles_goal)
        else:
            keep_moving(tic, speed, cycles_goal)

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika.")

    finally:
        try:
            tic.enter_safe_start()
            tic.deenergize()
        except Exception:
            pass
        print("Silnik odłączony, safe start aktywny.")

        try:
            input("Naciśnij Enter, aby zakończyć...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
