# =============================================================================
# Operator console for tutorial_HIL_driver.py (PART 4)
#
# A small pygame window.  Hold the arrow keys to drive; the console sends
# "steering,throttle,braking" over UDP at 50 Hz to the simulation and prints
# the telemetry the simulation sends back (PART 4).  pygame is here only to
# capture live keypresses in a second terminal/machine - the readout below is
# plain text, not a hand-drawn dashboard; the sim's own Irrlicht window
# already has a built-in one (see PART 5 in tutorial_HIL_driver.py).
#
#   python operator_console.py                # simulation on this machine
#   python operator_console.py 192.168.1.20   # simulation on another machine
#
# Nothing here depends on Chrono - this could be a phone, a web page, a ROS
# node or a driving-simulator cockpit.  The interface is three floats.
# =============================================================================

import socket
import sys

import pygame

SIM_HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
SIM_PORT = 9870
SEND_HZ = 50

# How fast the key targets ramp (units per second)
STEER_RATE = 1.5
PEDAL_RATE = 2.0
STEER_RETURN = 3.0   # steering self-centers when no key is held

pygame.init()
screen = pygame.display.set_mode((480, 220))
pygame.display.set_caption(f"Operator console -> {SIM_HOST}:{SIM_PORT}")
font = pygame.font.SysFont("monospace", 18)
clock = pygame.time.Clock()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setblocking(False)

steering, throttle, braking = 0.0, 0.0, 0.0
telemetry = None


def line(y, text):
    screen.blit(font.render(text, True, (220, 220, 220)), (20, y))


running = True
while running:
    dt = clock.tick(SEND_HZ) / 1000.0
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
            running = False

    # --- keyboard -> target inputs ------------------------------------------
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        steering = min(1.0, steering + STEER_RATE * dt)     # +1 = left in Chrono
    elif keys[pygame.K_RIGHT]:
        steering = max(-1.0, steering - STEER_RATE * dt)
    else:  # self-center
        steering -= max(-STEER_RETURN * dt, min(STEER_RETURN * dt, steering))
    if keys[pygame.K_UP]:
        throttle = min(1.0, throttle + PEDAL_RATE * dt)
        braking = 0.0
    elif keys[pygame.K_DOWN]:
        braking = min(1.0, braking + PEDAL_RATE * dt)
        throttle = 0.0
    else:
        throttle = max(0.0, throttle - PEDAL_RATE * dt)
        braking = max(0.0, braking - PEDAL_RATE * dt)
    if keys[pygame.K_SPACE]:
        steering, throttle, braking = 0.0, 0.0, 0.0

    # --- send to the simulation ---------------------------------------------
    sock.sendto(f"{steering:.3f},{throttle:.3f},{braking:.3f}".encode(), (SIM_HOST, SIM_PORT))

    # --- PART 4: receive telemetry ------------------------------------------
    while True:
        try:
            data, _ = sock.recvfrom(256)
            telemetry = tuple(float(x) for x in data.decode().split(","))
            # (sim time, speed, RTF, lateral acc, applied steering, throttle, braking)
        except (BlockingIOError, ValueError):
            break

    # --- draw: plain text, nothing hand-drawn --------------------------------
    screen.fill((25, 25, 30))
    line(15, "arrows: drive   space: reset   esc: quit")
    line(55, f"sent      steering {steering:+.2f}  throttle {throttle:.2f}  braking {braking:.2f}")

    if telemetry is None:
        line(95, "no telemetry (enable SEND_FEEDBACK in the sim)")
    else:
        t, speed, rtf, acc_y, ap_steer, ap_thr, ap_brk = telemetry
        line(95, f"applied   steering {ap_steer:+.2f}  throttle {ap_thr:.2f}  braking {ap_brk:.2f}")
        line(135, f"speed {speed * 3.6:6.1f} km/h   sim time {t:7.2f} s   RTF {rtf:.2f}")
        line(165, f"lateral acc {acc_y:+5.2f} m/s^2")

    pygame.display.flip()

pygame.quit()
