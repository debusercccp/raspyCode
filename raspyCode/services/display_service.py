"""
TFTDisplayService: scrive direttamente su /dev/fb1 (ILI9486 3.5", 480x320)
lo stato corrente dell'agente, senza script Bash intermedi ne' file
temporanei per il rendering (usa un canvas Pillow convertito RGB->RGB565
via numpy). Se /dev/fb1 non esiste (es. in esecuzione sul laptop, o Pi
senza HAT collegato) il servizio si disabilita silenziosamente e continua
a drenare la coda per non accumulare memoria, senza mai far crashare
il resto dell'agente.
"""
from pathlib import Path

from ..core.event_bus import EventBus
from ..core.events import Event, LLMToolCallEvent, StatusEvent, ToolResultEvent

FB_PATH = "/dev/fb1"
FB_WIDTH = 480
FB_HEIGHT = 320

_LEVEL_STYLE = {
    "info": ((10, 10, 20), (0, 255, 140)),
    "warning": ((60, 45, 0), (255, 200, 60)),
    "error": ((60, 10, 10), (255, 80, 80)),
}


class TFTDisplayService:
    def __init__(self, bus: EventBus) -> None:
        self._queue = bus.subscribe()
        self._enabled = Path(FB_PATH).exists()
        self._font = None
        if self._enabled:
            self._init_render_deps()

    def _init_render_deps(self) -> None:
        try:
            import numpy
            from PIL import Image, ImageDraw, ImageFont

            self._Image = Image
            self._ImageDraw = ImageDraw
            self._np = numpy
            try:
                self._font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18
                )
            except Exception:
                self._font = ImageFont.load_default()
        except ImportError:
            # Pillow/numpy assenti: disabilita il rendering, non crashare.
            self._enabled = False

    async def run(self) -> None:
        while True:
            event = await self._queue.get()
            if self._enabled:
                self._handle(event)
            self._queue.task_done()

    def _handle(self, event: Event) -> None:
        if isinstance(event, StatusEvent):
            self._render(event.text, event.level)
        elif isinstance(event, LLMToolCallEvent):
            self._render(f"[TOOL RUNNING]\n{event.tool_name}...", "info")
        elif isinstance(event, ToolResultEvent):
            level = "error" if event.is_error else "info"
            preview = event.result_output[:150]
            self._render(f"[{event.tool_name}]\n{preview}", level)

    def _render(self, text: str, level: str) -> None:
        bg, fg = _LEVEL_STYLE.get(level, _LEVEL_STYLE["info"])
        try:
            img = self._Image.new("RGB", (FB_WIDTH, FB_HEIGHT), bg)
            draw = self._ImageDraw.Draw(img)
            draw.text((10, 10), text, font=self._font, fill=fg)

            arr = self._np.array(img, dtype=self._np.uint8)
            r = (arr[:, :, 0] >> 3).astype(self._np.uint16)
            g = (arr[:, :, 1] >> 2).astype(self._np.uint16)
            b = (arr[:, :, 2] >> 3).astype(self._np.uint16)
            rgb565 = (r << 11) | (g << 5) | b
            buf = rgb565.astype("<u2").tobytes()  # little-endian, standard fbtft

            with open(FB_PATH, "wb") as fb:
                fb.write(buf)
        except OSError:
            # Scrittura fallita a runtime (permessi, display scollegato):
            # il display e' best-effort, non deve mai propagare l'errore.
            pass
