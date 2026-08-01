"""
TFTDisplayService: gira sul laptop (orion) e streamma i frame via
connessione TCP persistente al demone fb_listener sul Raspberry Pi (10.42.0.2).
"""

import socket
import threading
import time

from ..core.event_bus import EventBus
from ..core.events import (
    Event,
    LLMToolCallEvent,
    StatusEvent,
    SystemStatsEvent,
    ToolResultEvent,
    UserMessageEvent,
)

PI_IP = "10.42.0.2"
PORT = 9999
FB_WIDTH = 480
FB_HEIGHT = 320

_LEVEL_STYLE = {
    "info": ((10, 10, 20), (0, 255, 140)),
    "warning": ((60, 45, 0), (255, 200, 60)),
    "error": ((60, 10, 10), (255, 80, 80)),
}

_QUERY_MAX_CHARS = 120

# Colore ufficiale del logo Raspberry Pi (il "berry" rosso/magenta della
# fondazione, riprodotto proceduralmente con PIL — nessuna immagine esterna).
_BERRY_RED = (203, 34, 90)
_LEAF_GREEN = (117, 174, 63)

# Catena di font monospace con fallback: proviamo prima la Bold (piu'
# leggibile su un TFT piccolo), poi alternative comuni su Debian/Raspberry
# Pi OS se DejaVu non fosse installato.
_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/opentype/noto/NotoSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]
_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/opentype/noto/NotoSansMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


class TFTDisplayService:
    def __init__(self, bus: EventBus) -> None:
        self._queue = bus.subscribe()
        self._enabled = True
        self._font = None
        self._font_small = None
        self._font_title = None

        self._last_query: str = ""
        self._last_status_text: str = "In attesa..."
        self._last_status_level: str = "info"
        self._last_stats: SystemStatsEvent | None = None
        # Finche' non arriva il primo evento vero, mostriamo lo splash
        # Raspberry invece della schermata di stato vuota.
        self._show_splash = True

        # Gestione socket persistente in background
        self._socket = None
        self._lock = threading.Lock()

        if self._enabled:
            self._init_render_deps()
            # Avvia il thread che mantiene vivo il socket
            threading.Thread(target=self._maintain_connection, daemon=True).start()

    def _init_render_deps(self) -> None:
        try:
            import numpy
            from PIL import Image, ImageDraw, ImageFont

            self._Image = Image
            self._ImageDraw = ImageDraw
            self._np = numpy
            self._font_title = self._load_font(_FONT_CANDIDATES_BOLD, 26, ImageFont)
            self._font = self._load_font(_FONT_CANDIDATES_BOLD, 18, ImageFont)
            self._font_small = self._load_font(_FONT_CANDIDATES_REGULAR, 14, ImageFont)
        except ImportError:
            self._enabled = False

    @staticmethod
    def _load_font(candidates: list[str], size: int, image_font_module):
        for path in candidates:
            try:
                return image_font_module.truetype(path, size)
            except Exception:
                continue
        return image_font_module.load_default()

    def _maintain_connection(self) -> None:
        """Mantiene il socket costantemente connesso al Pi, ripristinandolo se cade."""
        while True:
            if self._socket is None:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5.0)
                    s.connect((PI_IP, PORT))
                    with self._lock:
                        self._socket = s
                    # Appena la connessione e' viva, mandiamo subito lo
                    # splash Raspberry (o l'ultimo stato noto) cosi' il
                    # display non resta nero in attesa del primo evento.
                    self._render()
                except Exception:
                    time.sleep(3)
            else:
                time.sleep(1)

    async def run(self) -> None:
        while True:
            event = await self._queue.get()
            if self._enabled:
                self._handle(event)
            self._queue.task_done()

    def _handle(self, event: Event) -> None:
        redraw = False
        # Il primo evento reale chiude lo splash e passa alla UI di stato.
        self._show_splash = False

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

    def _draw_raspberry_icon(self, draw, cx: float, cy: float, scale: float) -> None:
        """Disegna un logo Raspberry Pi stilizzato usando solo primitive
        PIL (ellissi): 5 "lobi" per il berry rosso/magenta e 2 foglie
        verdi in alto. Nessuna immagine esterna richiesta."""
        r = 16 * scale
        # Cinque lobi del berry disposti a raggiera, come nel logo ufficiale
        offsets = [
            (0.0, -r * 0.55),
            (-r * 0.85, -r * 0.05),
            (r * 0.85, -r * 0.05),
            (-r * 0.55, r * 0.75),
            (r * 0.55, r * 0.75),
        ]
        for dx, dy in offsets:
            x, y = cx + dx, cy + dy
            draw.ellipse((x - r, y - r, x + r, y + r), fill=_BERRY_RED)

        # Due foglioline in alto
        leaf_w, leaf_h = r * 0.9, r * 0.5
        draw.ellipse(
            (
                cx - leaf_w - r * 0.15,
                cy - r * 1.5,
                cx - r * 0.15,
                cy - r * 1.5 + leaf_h,
            ),
            fill=_LEAF_GREEN,
        )
        draw.ellipse(
            (
                cx + r * 0.15,
                cy - r * 1.5,
                cx + r * 0.15 + leaf_w,
                cy - r * 1.5 + leaf_h,
            ),
            fill=_LEAF_GREEN,
        )

    def _text_width(self, draw, text: str, font) -> int:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0]
        except Exception:
            return len(text) * 10

    def _render_splash(self, draw) -> None:
        """Schermata iniziale mostrata al boot / alla riconnessione, prima
        che arrivi il primo evento reale sul bus."""
        self._draw_raspberry_icon(draw, FB_WIDTH / 2, FB_HEIGHT / 2 - 40, scale=1.6)

        title = "raspyCode"
        title_w = self._text_width(draw, title, self._font_title)
        draw.text(
            (FB_WIDTH / 2 - title_w / 2, FB_HEIGHT / 2 + 30),
            title,
            font=self._font_title,
            fill=(230, 230, 230),
        )

        subtitle = "In attesa..."
        sub_w = self._text_width(draw, subtitle, self._font_small)
        draw.text(
            (FB_WIDTH / 2 - sub_w / 2, FB_HEIGHT / 2 + 66),
            subtitle,
            font=self._font_small,
            fill=(120, 120, 120),
        )

    def _render(self) -> None:
        bg, fg = _LEVEL_STYLE.get(self._last_status_level, _LEVEL_STYLE["info"])
        try:
            canvas_bg = (12, 12, 16) if self._show_splash else bg
            img = self._Image.new("RGB", (FB_WIDTH, FB_HEIGHT), canvas_bg)
            draw = self._ImageDraw.Draw(img)

            if self._show_splash:
                self._render_splash(draw)
            else:
                # Piccolo logo Raspberry persistente in alto a destra, per
                # branding, su tutte le schermate di stato.
                self._draw_raspberry_icon(draw, FB_WIDTH - 24, 20, scale=0.35)

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

                # Sezione stats (in fondo)
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
            buf = rgb565.astype("<u2").tobytes()

            # Invio asincrono "spara e dimentica" sul socket persistente
            threading.Thread(target=self._send_frame, args=(buf,), daemon=True).start()
        except Exception:
            pass

    def _send_frame(self, buf: bytes) -> None:
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.sendall(buf)
                except Exception:
                    # Se l'invio fallisce, chiudiamo il socket corrotto:
                    # il thread di manutenzione lo riattiverà al volo
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None
