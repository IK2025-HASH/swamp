"""
android_utils.py — Helpers for Android-specific APIs via pyjnius.

On Android:  uses MediaProjection, ContentResolver, etc.
On desktop:  falls back to PIL / mock data for testing.
"""

import io
import logging
import os
import threading
from typing import Optional, List, Dict

from kivy.utils import platform

logger = logging.getLogger(__name__)

IS_ANDROID = platform == "android"

# ---------------------------------------------------------------------------
# Lazy imports for Android / desktop
# ---------------------------------------------------------------------------

_jnius_available = False
if IS_ANDROID:
    try:
        from jnius import autoclass, cast, PythonJavaClass, java_method  # type: ignore
        _jnius_available = True
    except ImportError:
        logger.warning("pyjnius not available on Android build — some features disabled")

_pil_available = False
try:
    from PIL import Image, ImageGrab  # type: ignore
    _pil_available = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def get_external_storage_path() -> str:
    """Return writable external storage directory."""
    if IS_ANDROID and _jnius_available:
        try:
            Environment = autoclass("android.os.Environment")
            path = Environment.getExternalStorageDirectory().getAbsolutePath()
            return path
        except Exception as e:
            logger.error("get_external_storage_path: %s", e)
    # Desktop fallback
    return os.path.expanduser("~/swamp_files")


def ensure_swamp_dir() -> str:
    """Ensure and return the Swamp working directory."""
    base = get_external_storage_path()
    swamp_dir = os.path.join(base, "Swamp")
    os.makedirs(swamp_dir, exist_ok=True)
    return swamp_dir


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def read_contacts() -> List[Dict[str, str]]:
    """
    Read device contacts via ContentResolver (Android) or return mock data (desktop).

    Returns list of dicts: [{"name": "...", "phone": "..."}, ...]
    """
    if IS_ANDROID and _jnius_available:
        return _read_contacts_android()
    else:
        return _mock_contacts()


def _read_contacts_android() -> List[Dict[str, str]]:
    contacts = []
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        context = PythonActivity.mActivity
        cr = context.getContentResolver()

        ContactsContract = autoclass("android.provider.ContactsContract")
        Contacts = autoclass("android.provider.ContactsContract$Contacts")
        Phone = autoclass("android.provider.ContactsContract$CommonDataKinds$Phone")

        cursor = cr.query(
            Contacts.CONTENT_URI,
            None, None, None,
            "display_name ASC",
        )
        if cursor is None:
            return contacts

        id_col = cursor.getColumnIndex(Contacts._ID)
        name_col = cursor.getColumnIndex(Contacts.DISPLAY_NAME_PRIMARY)

        while cursor.moveToNext():
            contact_id = cursor.getString(id_col)
            name = cursor.getString(name_col) or ""

            # Fetch phone numbers
            phone_cursor = cr.query(
                Phone.CONTENT_URI,
                None,
                f"{Phone.CONTACT_ID} = ?",
                [contact_id],
                None,
            )
            phones = []
            if phone_cursor:
                phone_col = phone_cursor.getColumnIndex(Phone.NUMBER)
                while phone_cursor.moveToNext():
                    num = phone_cursor.getString(phone_col)
                    if num:
                        phones.append(num)
                phone_cursor.close()

            contacts.append({"name": name, "phone": ", ".join(phones)})

        cursor.close()
    except Exception as e:
        logger.error("_read_contacts_android: %s", e)
    return contacts


def _mock_contacts() -> List[Dict[str, str]]:
    return [
        {"name": "Alice Example", "phone": "+1-555-0101"},
        {"name": "Bob Example", "phone": "+1-555-0102"},
        {"name": "Carol Example", "phone": "+1-555-0103"},
    ]


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def get_clipboard_text() -> str:
    """Read clipboard text from Android ClipboardManager or kivy Clipboard."""
    if IS_ANDROID and _jnius_available:
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            context = PythonActivity.mActivity
            ClipboardManager = autoclass("android.content.ClipboardManager")
            clipboard = cast(
                ClipboardManager,
                context.getSystemService("clipboard"),
            )
            clip = clipboard.getPrimaryClip()
            if clip and clip.getItemCount() > 0:
                return str(clip.getItemAt(0).coerceToText(context))
        except Exception as e:
            logger.error("get_clipboard_text Android: %s", e)
    # Desktop fallback via kivy
    try:
        from kivy.core.clipboard import Clipboard as KivyClipboard
        return KivyClipboard.paste() or ""
    except Exception:
        return ""


def set_clipboard_text(text: str):
    """Write text to clipboard."""
    if IS_ANDROID and _jnius_available:
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            context = PythonActivity.mActivity
            ClipboardManager = autoclass("android.content.ClipboardManager")
            ClipData = autoclass("android.content.ClipData")
            clipboard = cast(
                ClipboardManager,
                context.getSystemService("clipboard"),
            )
            clip = ClipData.newPlainText("swamp", text)
            clipboard.setPrimaryClip(clip)
            return
        except Exception as e:
            logger.error("set_clipboard_text Android: %s", e)
    try:
        from kivy.core.clipboard import Clipboard as KivyClipboard
        KivyClipboard.copy(text)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

class ScreenCaptureSession:
    """
    Manages screen capture.

    On Android: uses MediaProjection API via pyjnius (requires FOREGROUND_SERVICE
    permission and user consent via the system dialog).
    On desktop: uses PIL.ImageGrab.
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_callback = None  # callable(jpeg_bytes, width, height)

        # Android-specific state
        self._media_projection = None
        self._image_reader = None
        self._virtual_display = None

    def start(self, frame_callback, fps: int = 5):
        """
        Start capture loop.

        Args:
            frame_callback: called with (jpeg_bytes: bytes, width: int, height: int)
            fps: target frames per second
        """
        if self._running:
            return
        self._running = True
        self._frame_callback = frame_callback

        if IS_ANDROID and _jnius_available:
            self._thread = threading.Thread(
                target=self._android_capture_loop,
                args=(fps,),
                daemon=True,
            )
        else:
            self._thread = threading.Thread(
                target=self._desktop_capture_loop,
                args=(fps,),
                daemon=True,
            )
        self._thread.start()
        logger.info("ScreenCaptureSession started (%d fps)", fps)

    def stop(self):
        """Stop the capture loop."""
        self._running = False
        if self._virtual_display:
            try:
                self._virtual_display.release()
            except Exception:
                pass
            self._virtual_display = None
        if self._media_projection:
            try:
                self._media_projection.stop()
            except Exception:
                pass
            self._media_projection = None
        logger.info("ScreenCaptureSession stopped")

    # ------------------------------------------------------------------
    # Android capture via MediaProjection + ImageReader
    # ------------------------------------------------------------------

    def _android_capture_loop(self, fps: int):
        import time
        interval = 1.0 / fps
        try:
            # Acquire MediaProjection
            self._media_projection = _get_media_projection()
            if self._media_projection is None:
                logger.error("Could not obtain MediaProjection")
                self._running = False
                return

            metrics = _get_display_metrics()
            width, height, density = metrics

            # Create ImageReader
            ImageReader = autoclass("android.media.ImageReader")
            PixelFormat = autoclass("android.graphics.PixelFormat")
            self._image_reader = ImageReader.newInstance(
                width, height, PixelFormat.RGBA_8888, 2
            )

            # Create VirtualDisplay
            DisplayManager = autoclass("android.hardware.display.DisplayManager")
            self._virtual_display = self._media_projection.createVirtualDisplay(
                "SwampCapture",
                width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                self._image_reader.getSurface(),
                None, None,
            )

            while self._running:
                t0 = time.monotonic()
                try:
                    image = self._image_reader.acquireLatestImage()
                    if image is not None:
                        jpeg_bytes = _android_image_to_jpeg(image, width, height)
                        image.close()
                        if jpeg_bytes and self._frame_callback:
                            self._frame_callback(jpeg_bytes, width, height)
                except Exception as e:
                    logger.error("Android capture frame error: %s", e)

                elapsed = time.monotonic() - t0
                sleep_time = max(0.0, interval - elapsed)
                time.sleep(sleep_time)

        except Exception as e:
            logger.error("_android_capture_loop error: %s", e)
            self._running = False

    # ------------------------------------------------------------------
    # Desktop capture via PIL
    # ------------------------------------------------------------------

    def _desktop_capture_loop(self, fps: int):
        import time
        interval = 1.0 / fps

        if not _pil_available:
            logger.warning("PIL not available; generating placeholder frames")

        while self._running:
            t0 = time.monotonic()
            try:
                jpeg_bytes, w, h = _desktop_capture_frame()
                if jpeg_bytes and self._frame_callback:
                    self._frame_callback(jpeg_bytes, w, h)
            except Exception as e:
                logger.error("Desktop capture frame error: %s", e)

            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))


# ---------------------------------------------------------------------------
# Android helpers
# ---------------------------------------------------------------------------

_media_projection_instance = None  # set externally by the Activity result handler


def set_media_projection(projection):
    """Called from the Android activity result handler to store the projection."""
    global _media_projection_instance
    _media_projection_instance = projection
    logger.info("MediaProjection instance stored")


def request_media_projection_permission():
    """
    Launch the system MediaProjection consent dialog.
    The result must be caught by the Android Activity and passed to set_media_projection().
    """
    if not (IS_ANDROID and _jnius_available):
        logger.info("request_media_projection_permission: not on Android")
        return
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        MediaProjectionManager = autoclass("android.media.projection.MediaProjectionManager")
        mpm = cast(
            MediaProjectionManager,
            activity.getSystemService("media_projection"),
        )
        intent = mpm.createScreenCaptureIntent()
        activity.startActivityForResult(intent, 1001)  # request code 1001
        logger.info("Launched MediaProjection consent dialog")
    except Exception as e:
        logger.error("request_media_projection_permission: %s", e)


def _get_media_projection():
    """Return the stored MediaProjection, requesting it if needed."""
    global _media_projection_instance
    if _media_projection_instance is not None:
        return _media_projection_instance
    # Try to request
    request_media_projection_permission()
    # Wait briefly for the result (the actual grant arrives asynchronously)
    import time
    for _ in range(30):
        if _media_projection_instance is not None:
            return _media_projection_instance
        time.sleep(0.5)
    return None


def _get_display_metrics():
    """Return (width, height, density) for the primary display."""
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        DisplayMetrics = autoclass("android.util.DisplayMetrics")
        metrics = DisplayMetrics()
        activity.getWindowManager().getDefaultDisplay().getMetrics(metrics)
        return metrics.widthPixels, metrics.heightPixels, metrics.densityDpi
    except Exception as e:
        logger.error("_get_display_metrics: %s", e)
        return 1080, 1920, 320


def _android_image_to_jpeg(image, width: int, height: int) -> Optional[bytes]:
    """Convert an android.media.Image (RGBA_8888) to a JPEG bytes."""
    try:
        planes = image.getPlanes()
        buffer = planes[0].getBuffer()
        row_stride = planes[0].getRowStride()
        pixel_stride = planes[0].getPixelStride()

        # Copy buffer to Python bytes
        buf_size = buffer.remaining()
        raw = bytes(buffer.array()[:buf_size]) if hasattr(buffer, "array") else bytes(buf_size)

        if not _pil_available:
            return None

        img = Image.frombytes(
            "RGBA",
            (row_stride // pixel_stride, height),
            raw,
            "raw", "RGBA",
        )
        # Crop to actual width
        img = img.crop((0, 0, width, height))
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        return buf.getvalue()
    except Exception as e:
        logger.error("_android_image_to_jpeg: %s", e)
        return None


# ---------------------------------------------------------------------------
# Desktop capture helper
# ---------------------------------------------------------------------------

def _desktop_capture_frame():
    """Capture desktop screenshot, return (jpeg_bytes, width, height)."""
    if _pil_available:
        try:
            img = ImageGrab.grab()
            w, h = img.size
            # Downscale for bandwidth
            scale = min(1.0, 720 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                w, h = img.size
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            return buf.getvalue(), w, h
        except Exception as e:
            logger.debug("ImageGrab failed (%s); generating placeholder", e)

    # Placeholder: 320x240 grey JPEG
    if _pil_available:
        try:
            img = Image.new("RGB", (320, 240), color=(80, 80, 80))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            return buf.getvalue(), 320, 240
        except Exception:
            pass
    return b"", 320, 240
