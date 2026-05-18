"""QR code generation and decoding utilities."""
import json
import socket
from typing import Optional

# Guard all imports
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def generate_qr_payload(name: str, ip: str, port: int, role: str, node_id: str) -> str:
    """Return a compact JSON string encoding the peer info for QR display."""
    return json.dumps({"n": name, "ip": ip, "p": port, "r": role, "id": node_id},
                      separators=(",", ":"))


def parse_qr_payload(payload: str) -> Optional[dict]:
    """Parse a QR payload string; return normalised dict or None on failure."""
    try:
        raw = json.loads(payload)
        return {
            "name": raw["n"],
            "ip": raw["ip"],
            "port": int(raw["p"]),
            "role": raw["r"],
            "node_id": raw["id"],
        }
    except Exception:
        return None


def generate_qr_image(data: str, size: int = 300):
    """
    Generate a PIL Image containing the QR code for *data*.

    Returns a PIL RGBA Image, or None if qrcode / PIL are unavailable.
    """
    if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
        return None
    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.convert("RGBA")
        img = img.resize((size, size), PILImage.NEAREST)
        return img
    except Exception:
        return None


def pil_to_kivy_texture(pil_img):
    """
    Convert a PIL RGBA image to a Kivy Texture.

    Kivy's coordinate system has (0,0) at the bottom-left, so we must
    flip the image vertically before loading the pixel data.
    """
    from kivy.graphics.texture import Texture

    img_rgba = pil_img.convert("RGBA")
    img_rgba = img_rgba.transpose(PILImage.FLIP_TOP_BOTTOM)
    data = img_rgba.tobytes()
    texture = Texture.create(size=img_rgba.size, colorfmt="rgba")
    texture.blit_buffer(data, colorfmt="rgba", bufferfmt="ubyte")
    return texture


def decode_qr_from_pil(pil_img) -> Optional[str]:
    """
    Attempt to decode the first QR code found in *pil_img*.

    Returns the decoded string, or None if decoding fails or pyzbar is absent.
    """
    if not PYZBAR_AVAILABLE or not PIL_AVAILABLE:
        return None
    try:
        results = pyzbar.decode(pil_img)
        for obj in results:
            if obj.data:
                return obj.data.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def get_local_ip() -> str:
    """
    Return the LAN IP address of this device.

    Uses a UDP connect trick (no actual packet is sent) to discover
    the default outbound interface.  Falls back to 127.0.0.1.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
