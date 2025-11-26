#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import keyboard
from ticlib import TicUSB

# -------- DOMYŚLNA KONFIGURACJA (można nadpisać z CLI) --------
X1_DEFAULT = -1100                   # punkt krańcowy 1 (µkroki)
X2_DEFAULT =  1100                   # punkt krańcowy 2 (µkroki)
CYCLES_DEFAULT = 10                  # liczba pełnych cykli (x1->x2->x1 lub x2->x1->x2)

DWELL_S = 0.3                        # pauza na krańcu
TOLERANCE = 50                       # akceptowalny błąd pozycji [µkroki]
TIMEOUT_S = 60                       # maks. oczekiwanie na dojazd jednego odcinka
KEEPALIVE_PERIOD = 0.05              # reset command timeout co ...

# Limity ruchu

SET_LIMITS = True
MAX_SPEED = 60_000_000
MAX_ACCEL = 2_000_000
MAX_DECEL = 2*MAX_ACCEL
START_SPEED = 0


def parse_cli():
    """
    Użycie:
      python oscylacja.py [cycles] [x1] [x2]
    Wszystko opcjonalne.
    """
    cycles, x1, x2 = CYCLES_DEFAULT, X1_DEFAULT, X2_DEFAULT
    try:
        if len(sys.argv) >= 2: cycles = int(sys.argv[1])
        if len(sys.argv) >= 3: x1 = int(sys.argv[2])
        if len(sys.argv) >= 4: x2 = int(sys.argv[3])
    except ValueError:
        print("Uwaga: błędny argument CLI — używam wartości domyślnych.")
        cycles, x1, x2 = CYCLES_DEFAULT, X1_DEFAULT, X2_DEFAULT
    if x1 == x2:
        raise ValueError("x1 i x2 nie mogą być równe.")
    return x1, x2, cycles

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

def make_cycles(tic: TicUSB, x1: int, x2: int, cycles_goal: int):
    try:
        cur = tic.get_current_position()
        # Wybierz bliższy punkt na start
        first_target = x1 if abs(cur - x1) <= abs(cur - x2) else x2
        second_target = x2 if first_target == x1 else x1

        print(f"Start. Pozycja bieżąca: {cur} µkroków. x1={x1}, x2={x2}, cycles={cycles_goal}")
        print(f"Pierwszy cel: {first_target}")

        counter = 0
        while counter < cycles_goal:
            move_and_wait(tic, first_target)
            time.sleep(DWELL_S)
            move_and_wait(tic, second_target)
            time.sleep(DWELL_S)
            move_and_wait(tic, 0)
            counter += 1

             #Reset


    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika.")
    finally:
        try:
            tic.enter_safe_start()
            tic.deenergize()
        except Exception:
            pass
        print("Silnik odłączony, safe start aktywny.")


def manual_move(tic):
    STEP = 50.0
    SPEED = int(MAX_SPEED / 3)
    tic.set_max_speed(SPEED)

    print("Sterowanie ręczne:")
    print("Hold [a] or [d] to set position, [q] = Quit")
    try:
        while True:
            if keyboard.is_pressed("a"):
                tic.set_target_velocity(-SPEED)

            elif keyboard.is_pressed("d"):
                tic.set_target_velocity(SPEED)
            else:
                tic.set_target_velocity(0)

            if keyboard.is_pressed("q"):
                break

            tic.reset_command_timeout()
            print("Position:", tic.get_current_position())


    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika (manual).")
    finally:
        tic.halt_and_set_position(0)
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [manual]")


def safe_shutdown(tic):
    if tic is None:
        return
    try:
        if hasattr(tic, "set_target_velocity"):
            try:
                tic.set_target_velocity(0)
            except Exception:
                pass
        if hasattr(tic, "enter_safe_start"):
            try:
                tic.enter_safe_start()
            except Exception as e:
                print(f"[WARN] enter_safe_start failed: {e}", file=sys.stderr)

        if hasattr(tic, "deenergize"):
            try:
                tic.deenergize()
            except Exception as e:
                print(f"[WARN] deenergize failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] cleanup wrapper failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    x1, x2, cycles_goal = parse_cli()
    tic = TicUSB()
    tic.energize()
    tic.exit_safe_start()
    tic.halt_and_set_position(0) #THIS MUST BE HERE TO START FROM 0.

    if SET_LIMITS:
        tic.set_starting_speed(START_SPEED)
        tic.set_max_speed(MAX_SPEED)
        tic.set_max_acceleration(int(MAX_ACCEL*0.8)) #Żeby nie szarpało strasznie
        tic.set_max_deceleration(int(MAX_DECEL*0.8))

    try:
        print(tic.get_current_position())
        # make_cycles(tic, x2, x1, cycles_goal)
        manual_move(tic)                          #<- manual move A,D to set start point

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika (main).")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)

    finally:
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [main]")