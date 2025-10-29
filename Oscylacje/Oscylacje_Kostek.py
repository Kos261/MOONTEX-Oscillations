#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import keyboard
from ticlib import TicUSB

# Default values
X1_DEFAULT = -1100                   # punkt krańcowy 1 (µkroki)
X2_DEFAULT =  1100                   # punkt krańcowy 2 (µkroki)
CYCLES_DEFAULT = 10                  # liczba pełnych cykli (x1->x2->x1 lub x2->x1->x2)

DWELL_S = 0.5                        # pauza na krańcu
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
    wait_until_reached(tic, int(target), TIMEOUT_S, TOLERANCE)
    return wait_until_reached(tic, target, TIMEOUT_S, TOLERANCE)

def test_move(tic):
    x1 =-300
    x2 = 600
    x3 = -300
    try:
        start = tic.get_current_position()
        print(f"Start. Pozycja bieżąca: {start} µkroków. x1={x1}, x2={x2}")

        time.sleep(DWELL_S)
        print(f"-> Jadę do {x1}")
        move_and_wait(tic, x1)
        print(f"Osiągnięto {x1}")
        time.sleep(DWELL_S)

        print(f"-> Jadę do {x2}")
        move_and_wait(tic, x2)   #!UWAGA TUTAJ ZMIANA
        print(f"Osiągnięto {x2}")
        time.sleep(DWELL_S)

        print(f"-> Jadę do {x3}")
        move_and_wait(tic, x3)  # !UWAGA TUTAJ ZMIANA
        print(f"Osiągnięto {x3}")
        time.sleep(DWELL_S)

        cur = tic.get_current_position()
        if abs(cur - start) < TOLERANCE:
            print("Ended in start pos. Good job!")

        # reset_pos(tic, start)

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika (cycles).")

    finally:
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [cycles]")

def manual_move(tic):
    STEP = -50.0
    SPEED = int(MAX_SPEED/3)
    tic.set_max_speed(SPEED)
    try:
        move_and_wait(tic, int(STEP*4.0))

    # print("Sterowanie ręczne:")
    # print("Hold [a] or [d] to set position, [q] = Quit")
    # try:
    #     while True:
    #         if keyboard.is_pressed("a"):
    #             tic.set_target_velocity(-SPEED)
    #         elif keyboard.is_pressed("d"):
    #             tic.set_target_velocity(SPEED)
    #         else:
    #             tic.set_target_velocity(0)
    #
    #         if keyboard.is_pressed("q"):
    #             break
    #
    #         tic.reset_command_timeout()
    #         # time.sleep(0.05)
    #         print("Position:", tic.get_current_position())


    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika (manual).")
    finally:
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [manual]")

def make_cycles(tic, x1, x2, cycles_goal):
    try:
        cur = tic.get_current_position()
        # Wybierz bliższy punkt na start
        first_target = x1 if abs(cur - x1) <= abs(cur - x2) else x2
        other_target = x2 if first_target == x1 else x1

        print(f"Start. Pozycja bieżąca: {cur} µkroków. x1={x1}, x2={x2}, cycles={cycles_goal}")
        print(f"Pierwszy cel: {first_target}")

        # Liczenie pełnych cykli: cykl = powrót do 'anchor' po odwiedzeniu przeciwnego krańca
        anchor = first_target  # punkt startowy cyklu
        first_arrival_done = False  # ignorujemy pierwsze dotknięcie anchor na starcie
        visited_other_since_anchor = False  # czy odwiedzono przeciwległy kraniec od ostatniego anchor
        cycles_done = 0

        target = first_target
        while True:
            print(f"-> Jadę do {target}")
            move_and_wait(tic, target)
            print(f"Osiągnięto {target}")
            time.sleep(DWELL_S)

            # Aktualizacja stanu dla licznika cykli
            if not first_arrival_done:
                # pierwsze dojechanie do anchor na starcie — nie liczymy
                first_arrival_done = True
            else:
                if target != anchor:
                    # odwiedziliśmy przeciwległy kraniec
                    visited_other_since_anchor = True
                else:
                    # wróciliśmy do anchor
                    if visited_other_since_anchor:
                        cycles_done += 1
                        visited_other_since_anchor = False
                        print(f"Pełny cykl #{cycles_done} ukończony.")
                        if cycles_goal is not None and cycles_done >= cycles_goal:
                            print("Zakończono zaplanowaną liczbę pełnych cykli.")
                            break

            # Kolejny cel: przełącz na drugi kraniec
            target = other_target if target == first_target else first_target

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika.")
    finally:
        try:
            tic.enter_safe_start()
            tic.deenergize()
        except Exception:
            pass
        print("Silnik odłączony, safe start aktywny.")


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
    tic = None
    try:
        tic = TicUSB()
        tic.energize()
        tic.exit_safe_start()

        if SET_LIMITS:
            tic.set_starting_speed(START_SPEED)
            tic.set_max_speed(MAX_SPEED)
            tic.set_max_acceleration(MAX_ACCEL)
            tic.set_max_deceleration(MAX_DECEL)
            time.sleep(3)


        # test_move(tic)
        print("W ogole dziala")
        print("Typ Tic", type(tic))
        make_cycles(tic, x1, x2, cycles_goal)
        # manual_move(tic)

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika (main).")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)

    finally:
        safe_shutdown(tic)
        print("Silnik odłączony, safe start aktywny. [main]")