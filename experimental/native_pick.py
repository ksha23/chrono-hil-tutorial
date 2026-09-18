"""What the one-line SWIG change buys: mouse picking in ~25 portable lines.

Run against a Chrono built with %feature("director") irr::IEventReceiver:
    PYTHONPATH=<build>/bin python native_pick.py
"""
import pychrono as chrono
import pychrono.irrlicht as irr


class MouseReceiver(irr.IEventReceiver):
    """No Quartz, no CGWindowList, no NSEvent. No macOS. Just Irrlicht."""

    def __init__(self):
        super().__init__()
        self.x = self.y = 0
        self.down = False
        self.pressed = False          # edge, consumed by the loop
        self.keys = set()

    def OnEvent(self, ev):
        if ev.EventType == irr.EET_MOUSE_INPUT_EVENT:
            self.x, self.y = ev.MouseInput.X, ev.MouseInput.Y
            if ev.MouseInput.Event == irr.EMIE_LMOUSE_PRESSED_DOWN:
                self.down = self.pressed = True
            elif ev.MouseInput.Event == irr.EMIE_LMOUSE_LEFT_UP:
                self.down = False
        elif ev.EventType == irr.EET_KEY_INPUT_EVENT:
            (self.keys.add if ev.KeyInput.PressedDown else self.keys.discard)(int(ev.KeyInput.Key))
        return False                  # let Chrono's own GUI see it too


if __name__ == "__main__":
    import threading, time, os
    sys_ = chrono.ChSystemNSC()
    sys_.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
    mat = chrono.ChContactMaterialNSC()
    ball = chrono.ChBodyEasySphere(0.4, 1000, True, True, mat)
    ball.SetPos(chrono.ChVector3d(0, 0, 0.5)); ball.SetName("ball"); sys_.AddBody(ball)

    vis = irr.ChVisualSystemIrrlicht(); vis.AttachSystem(sys_)
    vis.SetCameraVertical(chrono.CameraVerticalDir_Z)
    vis.SetWindowTitle("native pick"); vis.SetWindowSize(640, 480); vis.Initialize()
    vis.AddTypicalLights(); vis.AddCamera(chrono.ChVector3d(0, -4, 0.5), chrono.ChVector3d(0, 0, 0.5))
    rx = MouseReceiver()
    vis.AddUserEventReceiver(rx)
    sys_.DoStepDynamics(1e-3)

    threading.Thread(target=lambda: (time.sleep(9), os._exit(0)), daemon=True).start()
    n = 0
    while vis.Run():
        if rx.pressed:
            rx.pressed = False
            print(f"  click at pixel ({rx.x},{rx.y}) - straight from Irrlicht, no OS calls")
        vis.BeginScene(); vis.Render(); vis.EndScene()
        sys_.DoStepDynamics(1e-3); n += 1
    print("frames:", n)
