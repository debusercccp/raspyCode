"""
TFTDisplayService: scrive direttamente su /dev/fb1 (ILI9486 3.5", 480x320)
lo stato corrente dell'agente, senza script Bash intermedi ne' file
temporanei per il rendering (usa un canvas Pillow convertito RGB->RGB565
via numpy). Se /dev/fb1 non esiste (es. in esecuzione sul laptop, o Pi
senza HAT collegato) il servizio si disabilita silenziosamente e continua
a drenare la coda per non accumulare memoria, senza mai far crashare
il resto dell'agente.

A differenza della versione precedente, questo servizio mantiene uno
stato (ultima query utente, ultime statistiche di sistema, ultimo status)
e ridisegna l'intero schermo componendo le tre sezioni, invece di
processare ogni evento in isolamento e perdere il resto.
"""

import os
from pathlib import Path

from ..core.event_bus import EventBus
from ..core.events import (
    Event,
    LLMToolCallEvent,
    StatusEvent,
    SystemStatsEvent,
    ToolResultEvent,
    UserMessageEvent,
)

FB_PATH = os.environ.get(
    "RASPY_FB_PATH", "/dev/fb0" if Path("/dev/fb0").exists() else "/dev/fb1"
)
FB_WIDTH = 480
FB_HEIGHT = 320

_LEVEL_STYLE = {
    "info": ((10, 10, 20), (0, 255, 140)),
    "warning": ((60, 45, 0), (255, 200, 60)),
    "error": ((60, 10, 10), (255, 80, 80)),
}

_QUERY_MAX_CHARS = 120  # troncamento per non far traboccare il canvas 480x320


class TFTDisplayService:
    def __init__(self, bus: EventBus) -> None:
        self._queue = bus.subscribe()
        self._enabled = Path(FB_PATH).exists()
        self._font = None
        self._font_small = None

        # Stato mantenuto tra un render e l'altro: senza questo, ogni
        # evento sovrascriveva tutto lo schermo perdendo query/stats
        # precedenti non correlate all'evento appena arrivato.
        self._last_query: str = ""
        self._last_status_text: str = "In attesa..."
        self._last_status_level: str = "info"
        self._last_stats: SystemStatsEvent | None = None

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
                self._font_small = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14
                )
            except Exception:
                self._font = ImageFont.load_default()
                self._font_small = self._font
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
        redraw = False

        if isinstance(event, UserMessageEvent):
            self._last_query = event.content[:_QUERY_MAX_CHARS]
            redraw = True
        elif isinstance(event, StatusEvent):
            self._last_status_text = event.text
            self._last_status_level = event.level
            redraw = True
        elif isinstance(event, LLMToolCallEvent):
            self._last_status_text = f"[TOOL RUNNING]\n{event.tool_name}..."
            self._last_status_level = "info"
            redraw = True
        elif isinstance(event, ToolResultEvent):
            self._last_status_level = "error" if event.is_error else "info"
            preview = event.result_output[:150]
            self._last_status_text = f"[{event.tool_name}]\n{preview}"
            redraw = True
        elif isinstance(event, SystemStatsEvent):
            self._last_stats = event
            redraw = True

        if redraw:
            self._render()

    def _stats_line(self) -> str:
        if self._last_stats is None:
            return "CPU: -- | RAM: -- | Temp: --"
        s = self._last_stats
        temp_str = f"{s.cpu_temp_c:.1f}C" if s.cpu_temp_c is not None else "n/d"
        return (
            f"Load: {s.cpu_load_1min:.2f} | "
            f"RAM: {s.mem_used_mb:.0f}/{s.mem_total_mb:.0f}MB | "
            f"Temp: {temp_str}"
        )

    def _render(self) -> None:
        bg, fg = _LEVEL_STYLE.get(self._last_status_level, _LEVEL_STYLE["info"])
        try:
            img = self._Image.new("RGB", (FB_WIDTH, FB_HEIGHT), bg)
            draw = self._ImageDraw.Draw(img)

            # Sezione query utente (in alto)
            draw.text(
                (10, 8),
                f"noya> {self._last_query}",
                font=self._font_small,
                fill=(120, 200, 255),
            )
            draw.line((10, 32, FB_WIDTH - 10, 32), fill=(60, 60, 60))

            # Sezione status/tool (centro)
            draw.text((10, 44), self._last_status_text, font=self._font, fill=fg)

            # Sezione stats (in fondo, sempre visibile)
            draw.line(
                (10, FB_HEIGHT - 30, FB_WIDTH - 10, FB_HEIGHT - 30),
                fill=(60, 60, 60),
            )
            draw.text(
                (10, FB_HEIGHT - 24),
                self._stats_line(),
                font=self._font_small,
                fill=(150, 150, 150),
            )

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
