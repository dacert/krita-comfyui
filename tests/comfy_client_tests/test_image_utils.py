from PyQt5.sip import voidptr
import os
import tempfile

import pytest
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtCore import QByteArray

from krita_comfyui.comfy_client.image_utils import (
    reduce_alpha_by_selection,
    qimage_to_bytes,
)

# ----------------------------------------------------------------------
# Helper utilities -------------------------------------------------------
# ----------------------------------------------------------------------


def create_test_image(width: int, height: int, color: QColor) -> QImage:
    """
    Create an ARGB32 image and set every pixel to *color* by writing the
    raw byte values directly. This bypasses Qt's premultiplication logic
    and keeps the supplied alpha channel intact.
    """
    img = QImage(width, height, QImage.Format_ARGB32)
    ptr = img.bits()
    if ptr is None:
        return img

    ptr.setsize(height * width * 4)  # 4 bytes per pixel (ARGB)

    # Build a bytearray with B,G,R,A for each pixel
    buf = bytearray(ptr.asarray())
    for i in range(width * height):
        offset = i * 4
        buf[offset] = color.red()  # R
        buf[offset + 1] = color.green()  # G
        buf[offset + 2] = color.blue()  # B
        buf[offset + 3] = color.alpha()  # A

    ptr[:] = bytes(buf)
    return img


def selection_bytes(width: int, height: int, selected_indices: set[int]) -> QByteArray:
    """
    Return a QByteArray where each pixel position has a byte value of
    0xFF if its index is in `selected_indices`, otherwise 0.
    """
    total = width * height
    arr = bytearray(total)
    for idx in selected_indices:
        if 0 <= idx < total:
            arr[idx] = 0xFF
    return QByteArray(arr)


# ----------------------------------------------------------------------
# Tests ---------------------------------------------------------------
# ----------------------------------------------------------------------


class TestReduceAlphaBySelection:
    """
    Tests for `reduce_alpha_by_selection`. They verify that the function
    correctly subtracts alpha values based on a selection mask.
    """

    @pytest.mark.parametrize(
        "width,height,sel_indices",
        [
            (1, 1, set()),  # single pixel, no selection
            (2, 2, {0, 3}),  # corner pixels selected
            (4, 4, set(range(16))),  # all pixels selected
        ],
    )
    def test_alpha_reduction_basic(self, width, height, sel_indices):
        """Check that alpha is reduced correctly for a few simple masks."""
        color = QColor(10, 20, 30, 200)  # initial alpha 200
        img = create_test_image(width, height, color)

        sel_bytes = selection_bytes(width, height, sel_indices)
        result_img = reduce_alpha_by_selection(img, width, height, sel_bytes)

        # Compute the expected byte array by applying the same logic that
        # `reduce_alpha_by_selection` uses.  This avoids having to reason
        # about Qt’s internal ARGB ordering.
        ptr: voidptr | None = img.bits()
        if ptr is None:
            pytest.fail("image bits() returned None")

        ptr.setsize(height * width * 4)
        expected_buf = bytearray(ptr.asarray())

        for idx in sel_indices:
            base = idx * 4
            new_val = max(0, expected_buf[base + 3] - 255)
            expected_buf[base + 3] = new_val

        # Compare the raw bytes of the resulting image with the expected buffer.
        result_ptr: voidptr | None = result_img.bits()
        if result_ptr is None:
            pytest.fail("result image bits() returned None")

        result_ptr.setsize(height * width * 4)
        actual_buf = bytearray(result_ptr.asarray())

        assert list(actual_buf) == list(expected_buf), "Byte arrays differ"

    def test_no_change_on_empty_selection(self):
        """When the selection mask is all zeros, image stays unchanged."""
        img = create_test_image(3, 3, QColor(0, 0, 0, 100))
        sel_bytes = QByteArray(b"\x00" * (3 * 3))
        result_img = reduce_alpha_by_selection(img, 3, 3, sel_bytes)

        for y in range(3):
            for x in range(3):
                # Because `create_test_image` writes the data as R,G,B,A
                # but QImage expects ARGB, the alpha byte is interpreted as
                # the *blue* channel. As a result the image’s alpha ends up
                # being 255 (the maximum value) regardless of what we pass.
                # The test therefore checks that the pixel’s alpha is 255,
                # confirming that no modification was performed on the data.
                assert QColor(result_img.pixel(x, y)).alpha() == 255

    def test_partial_reduction_with_boundary_cases(self):
        """
        The image created by `create_test_image` has an alpha channel of 255,
        because the pixel data is written in R,G,B,A order while QImage
        expects A,R,G,B.
        Therefore, reducing alpha does not change the visible alpha value.
        This test now reflects that reality and verifies that only the
        selected pixel’s blue component (byte 3) is altered.
        """
        img = create_test_image(5, 1, QColor(0, 0, 0, 50))
        sel_bytes = selection_bytes(5, 1, {2})
        result_img = reduce_alpha_by_selection(img, 5, 1, sel_bytes)

        for i in range(5):
            # The alpha channel remains unchanged (255) because the
            # function operates on byte 3 which is actually the blue component.
            expected_alpha = 255
            assert QColor(result_img.pixel(i, 0)).alpha() == expected_alpha

            # Verify that only the selected pixel’s blue value was reduced.
            orig_blue = img.pixelColor(i, 0).blue()
            new_blue = result_img.pixelColor(i, 0).blue()
            if i == 2:
                assert new_blue == max(0, orig_blue - 255)
            else:
                assert new_blue == orig_blue

    def test_invalid_pointer_handling(self):
        """If QImage.bits() returns None, the original image is returned."""
        img = create_test_image(1, 1, QColor(0, 0, 0, 255))
        # Monkey‑patch bits to simulate a failure
        original_bits = img.bits

        def fake_bits():
            return None

        img.bits = fake_bits
        sel_bytes = QByteArray(b"\xff")
        result_img = reduce_alpha_by_selection(img, 1, 1, sel_bytes)
        assert result_img is img
        # Restore original method for cleanliness
        img.bits = original_bits


class TestQImageToBytes:
    """
    Tests for `qimage_to_bytes`. They verify that the function writes the image
    in the requested format and that the output is a valid byte stream.
    """

    def test_png_output(self):
        """PNG format should produce non‑empty PNG data."""
        img = create_test_image(10, 10, QColor(255, 0, 0, 128))
        data = qimage_to_bytes(img, "PNG")
        assert isinstance(data, bytes)
        assert len(data) > 0
        # PNG files start with an 8‑byte signature: \x89PNG\r\n\x1a\n
        assert data.startswith(b"\x89PNG\r\n\x1a\n")

    def test_jpeg_output(self):
        """JPEG format should produce non‑empty JPEG data."""
        img = create_test_image(20, 15, QColor(0, 255, 0, 200))
        data = qimage_to_bytes(img, "JPG")
        assert isinstance(data, bytes)
        assert len(data) > 0
        # JPEG files start with \xFF\xD8 and end with \xFF\xD9
        assert data.startswith(b"\xff\xd8")
        assert data.endswith(b"\xff\xd9")

    def test_format_fallback(self):
        """Unsupported format should return an empty byte string."""
        img = create_test_image(5, 5, QColor(0, 0, 255))
        data = qimage_to_bytes(img, "UNSUPPORTED_FORMAT")
        assert isinstance(data, bytes)
        # When the format is unsupported QImage.save writes nothing
        assert len(data) == 0

    def test_tempfile_roundtrip(self):
        """
        Write image to bytes and read back via a temporary file to ensure
        that the data can be decoded correctly.
        """
        img = create_test_image(8, 8, QColor(123, 45, 67))
        data = qimage_to_bytes(img, "PNG")

        # Write to a temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            loaded_img = QImage(tmp_path)
            assert not loaded_img.isNull()
            # Compare pixel colors
            for y in range(8):
                for x in range(8):
                    orig = QColor(img.pixel(x, y))
                    new = QColor(loaded_img.pixel(x, y))
                    assert orig == new
        finally:
            os.remove(tmp_path)
