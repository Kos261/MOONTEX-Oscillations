#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import keyboard
from ticlib import TicUSB

KEEPALIVE_PERIOD = 0.05
TIMEOUT_S = 60
TOLERANCE = 50

SET_LIMITS = True
MAX_SPEED = 60_000_000
MAX_ACCEL = 2_000_000
MAX_DECEL = 2 * MAX_ACCEL
START_SPEED = 0

def _print_manual_help():
    print("""
[STEROWANIE RĘCZNE — skróty]
  a / d        — jazda w lewo / prawo (prędkość ciągła)
  SPACJA       — natychmiastowy STOP
  0            — jedź do pozycji 0
  z            — wyzeruj bieżącą pozycję (ustaw cur=0)
  strzałka ↑   — zwiększ prędkość max
  strzałka ↓   — zmniejsz prędkość max
  strzałka →   — zwiększ przyspieszenie/hamowanie
  strzałka ←   — zmniejsz przyspieszenie/hamowanie
  q            — wyjście z trybu ręcznego
""")

def wait_until_reached(tic, target, timeout_s=TIMEOUT_S, tolerance=TOLERANCE):
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
    return wait_until_reached(tic, int(target))

def safe_shutdown(tic):
    if tic is None:
        return
    try:
        try:
            tic.set_target_velocity(0)
        except Exception:
            pass
        try:
            tic.enter_safe_start()
        except Exception as e:
            print(f"[WARN] enter_safe_start failed: {e}", file=sys.stderr)
        try:
            tic.deenergize()
        except Exception as e:
            print(f"[WARN] deenergize failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] cleanup wrapper failed: {e}", file=sys.stderr)
# ==============================================================================


# ============================ STEROWANIE RĘCZNE ===============================
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
# ==============================================================================


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

def move(tic, speed = max(1, int(MAX_SPEED * 0.33))):
    zero = tic.get_current_position()
    counter = 0

    accel = max(1, int(MAX_ACCEL * 0.8))
    decel = max(1, int(MAX_DECEL * 0.8))

    tic.set_max_acceleration(accel)
    tic.set_max_deceleration(decel)
    tic.set_max_speed(speed)

    try:
        while True:
            pos = tic.get_current_position() % 400*18
            if pos >= 400*18:
                # tic.halt_and_set_position(0)
                counter += 1
                print("Cycle: ", counter)

            # print("POS: ",pos)
            tic.set_target_velocity(speed)
            if keyboard.is_pressed(" "):
                tic.set_target_velocity(0)
                return

            tic.reset_command_timeout()
    except KeyboardInterrupt:
        print("\n[MAN] Przerwano przez użytkownika.")

def main():
    tic = None
    try:
        print("Odpinamy narty")
        tic = init_and_configure()
        # _print_manual_help()
        manual_move(tic)
        # move(tic, speed=int(MAX_SPEED*0.4))
    except KeyboardInterrupt:
        print("\n[MAIN] Przerwano przez użytkownika.")
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
    finally:
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [kalibracja]")
        # przy dwukliku .exe okno nie zniknie od razu
        try:
            input("Naciśnij Enter, aby zamknąć...")
        except (EOFError, UnicodeDecodeError):
            pass


if __name__ == "__main__":
    main()
