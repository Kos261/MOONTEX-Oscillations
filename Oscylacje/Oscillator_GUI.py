from Oscillator_CLI import *
from Oscylacje import Oscillator_CLI

def oscillations(tic, x1, x2, speed, cycles_goal):
    # speed tu na razie nie maI
    Oscylacja_CLI.oscillations(tic, int(x1), int(x2), int(cycles_goal))

def keep_moving(tic, speed, cycles_goal):
    Oscylacja_CLI.keep_moving(tic, int(speed), int(cycles_goal))

def manual(tic):
    manual_move(tic)   # z Oscylacja_CLI

def _emergency_stop(tic):
    try:
        tic.halt_and_set_position(0)
        tic.set_target_velocity(0)
        tic.enter_safe_start()
        tic.deenergize()
    except Exception as e:
        print(e)