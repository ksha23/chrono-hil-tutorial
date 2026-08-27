# =============================================================================
# Operator console for tutorial_HIL_driver.py (PART 3 and PART 4)
#
# A small pygame window.  Hold the arrow keys to drive; the console sends
# "steering,throttle,braking" over UDP at 50 Hz to the simulation and shows the
# telemetry the simulation sends back (PART 4).
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
screen = pygame.display.set_mode((520, 300))
pygame.display.set_caption(f"Operator console -> {SIM_HOST}:{SIM_PORT}")
font = pygame.font.SysFont("monospace", 18)
big = pygame.font.SysFont("monospace", 40, bold=True)
clock = pygame.time.Clock()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setblocking(False)

steering, throttle, braking = 0.0, 0.0, 0.0
telemetry = None


def bar(x, y, w, h, value, lo, hi, color, applied=None):
    """Filled bar = what this console is sending; white tick = what the sim applied."""
    pygame.draw.rect(screen, (60, 60, 60), (x, y, w, h))
    frac = (value - lo) / (hi - lo)
    pygame.draw.rect(screen, color, (x, y, int(w * frac), h))
    if applied is not None:
        ax = x + int(w * (applied - lo) / (hi - lo))
        pygame.draw.rect(screen, (255, 255, 255), (ax - 2, y - 3, 4, h + 6))


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

    # --- draw ---------------------------------------------------------------
    screen.fill((25, 25, 30))
    screen.blit(font.render("arrows: drive   space: reset   esc: quit", True, (160, 160, 160)), (20, 15))
    applied = telemetry[4:7] if telemetry and len(telemetry) >= 7 else (None, None, None)
    screen.blit(font.render(f"steering {steering:+.2f}", True, (230, 230, 230)), (20, 55))
    bar(200, 55, 300, 20, steering, -1, 1, (80, 160, 255), applied[0])
    screen.blit(font.render(f"throttle {throttle:.2f}", True, (230, 230, 230)), (20, 85))
    bar(200, 85, 300, 20, throttle, 0, 1, (80, 220, 120), applied[1])
    screen.blit(font.render(f"braking  {braking:.2f}", True, (230, 230, 230)), (20, 115))
    bar(200, 115, 300, 20, braking, 0, 1, (240, 90, 80), applied[2])
    screen.blit(font.render("bar: sent   |: applied by the sim (smoothed)", True, (120, 120, 120)), (200, 138))

    if telemetry is None:
        screen.blit(font.render("no telemetry (enable SEND_FEEDBACK in the sim)", True, (120, 120, 120)), (20, 170))
    else:
        t, speed, rtf, acc_y = telemetry[:4]
        screen.blit(big.render(f"{speed * 3.6:5.1f} km/h", True, (255, 255, 255)), (20, 160))
        col = (80, 220, 120) if rtf <= 1.0 else (240, 90, 80)
        screen.blit(font.render(f"sim time {t:7.2f} s   RTF {rtf:.2f}", True, col), (20, 215))
        screen.blit(font.render(f"lateral acc {acc_y:+5.2f} m/s^2", True, (230, 230, 230)), (20, 245))
        bar(260, 245, 240, 18, acc_y, -8, 8, (200, 160, 60))

    pygame.display.flip()

pygame.quit()
