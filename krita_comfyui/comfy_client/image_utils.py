from PyQt5.QtGui import QImage
from PyQt5.QtCore import QBuffer, QIODevice


def reduce_alpha_by_selection(qimg: QImage, w: int, h: int, sel_bytes: bytearray) -> QImage:
    ptr = qimg.bits()
    ptr.setsize(h * w * 4)  # 4 bytes píxel (ARGB)
    buf = bytearray(ptr)

    total_pixels = w * h
    left_byte = 0
    right_byte = (total_pixels - 1) * 4

    while left_byte <= right_byte:
        idx_left = left_byte // 4
        if sel_bytes[idx_left] != 0:
            base = idx_left * 4
            selectedness = int.from_bytes(sel_bytes[idx_left], "big")
            new_alpha = buf[base + 3] - selectedness
            if new_alpha < 0:
                new_alpha = 0
            buf[base + 3] = new_alpha

        if right_byte > left_byte:
            idx_right = right_byte // 4
            if sel_bytes[idx_right] != 0:
                base = idx_right * 4
                selectedness = int.from_bytes(sel_bytes[idx_right], "big")
                new_alpha = buf[base + 3] - selectedness
                if new_alpha < 0:
                    new_alpha = 0
                buf[base + 3] = new_alpha

        left_byte += 4
        right_byte -= 4

    ptr[:] = bytes(buf)
    return qimg


def qimage_to_bytes(qimg: QImage, fmt: str = "PNG") -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    qimg.save(buffer, fmt)
    byte_array: bytes = bytes(buffer.data())
    return byte_array
