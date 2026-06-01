"""Three-component vector field widget."""

from __future__ import annotations

from lks_utils.gui_qt.components.fields.q_vector_field_base import QVectorFieldBase


class QVector3Field(QVectorFieldBase):
    """Field widget for 3D vectors."""

    COMPONENT_COUNT = 3

    def __init__(self, default_value: tuple[float, float, float], *, parent=None) -> None:
        super().__init__(default_value, vector_size=self.COMPONENT_COUNT, parent=parent)


__all__ = ["QVector3Field"]
