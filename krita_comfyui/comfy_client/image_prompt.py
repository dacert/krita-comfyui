import random
from dataclasses import dataclass, field

from PyQt5.QtCore import QByteArray, QRect


@dataclass
class ImagePrompt:
    """
    Represents a set of image filenames that all share the same ID.
    """

    image_id: str = field(default_factory=lambda: f"krita-{random.randint(1, 11768320141)}")
    image: str = field(init=False)
    mask: str = field(init=False)
    paint: str = field(init=False)
    painted: str = field(init=False)
    painted_mask: str = field(init=False)

    image_bytes: bytes | None = field(default=None, repr=False)

    sel_bytes: QByteArray | None = field(default=None, repr=False)
    inverted_sel_bytes: QByteArray | None = field(default=None, repr=False)
    sel_rect: QRect | None = field(default=None, repr=False)

    width: int = field(default=0, repr=False)
    height: int = field(default=0, repr=False)

    def __post_init__(self):
        # Build the dependent fields using the *instance*'s image_id
        self.image = f"{self.image_id}.png"
        self.mask = f"clipspace-mask-{self.image_id}.png"
        self.paint = f"clipspace-paint-{self.image_id}.png"
        self.painted = f"clipspace-painted-{self.image_id}.png"
        self.painted_mask = f"clipspace-painted-masked-{self.image_id}.png"

    def has_image_data(self) -> bool:
        return self.image_bytes is not None

    def has_selection_data(self) -> bool:
        return self.sel_bytes is not None
