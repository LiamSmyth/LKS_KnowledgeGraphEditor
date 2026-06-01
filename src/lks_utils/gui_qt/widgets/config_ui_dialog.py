"""Generic dialog for launching ConfigUI widgets."""
from __future__ import annotations

from typing import Any

try:
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
    from PySide6.QtCore import Qt
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False
    QDialog = object  # type: ignore

from lks_utils.gui_qt.theme.dark_theme import DARK_QSS


class QConfigUIDialog(QDialog):
    """
    Generic dialog that hosts a ConfigUI widget for a config dataclass.

    This dialog provides a reusable wrapper for any ConfigUI widget, adding
    OK/Cancel buttons and managing the config dataclass serialization.

    Usage:
        from lks_utils.image import ImageCompressionConfig, ImageCompressionConfigUI
        from lks_utils.gui_qt.widgets import QConfigUIDialog

        config = ImageCompressionConfig()
        result = QConfigUIDialog.edit_config(
            ImageCompressionConfigUI,
            config,
            title="Image Compression Settings"
        )
        if result is not None:
            # User clicked OK, result is the updated config
            process_image(image_path, result)

    Args:
        config_ui_class: ConfigUI class to instantiate (e.g., WhisperConfigUI)
        config: Current config dataclass instance
        title: Dialog window title
        parent: Parent widget

    Attributes:
        config_ui: The embedded ConfigUI widget instance
    """

    def __init__(
        self,
        config_ui_class: type,
        config: Any,
        title: str = "Configure",
        parent: Any = None,
    ) -> None:
        """Initialize the config UI dialog."""
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(500, 400)
        self.setStyleSheet(DARK_QSS)

        # Create the layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Instantiate and add the ConfigUI widget
        self.config_ui = config_ui_class(parent=self)
        self.config_ui.set_config(config)
        main_layout.addWidget(self.config_ui, stretch=1)

        # Create button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        main_layout.addLayout(button_layout)

    def get_config(self) -> Any:
        """
        Get the configured config dataclass from the embedded ConfigUI.

        Returns:
            Config dataclass populated from ConfigUI values
        """
        return self.config_ui.get_config()

    @staticmethod
    def edit_config(
        config_ui_class: type,
        config: Any,
        title: str = "Configure",
        parent: Any = None,
    ) -> Any | None:
        """
        Static convenience method to show dialog and get result.

        Opens a modal dialog with the ConfigUI widget. Returns the updated
        config on OK, or None if the user clicks Cancel.

        Args:
            config_ui_class: ConfigUI class to instantiate
            config: Current config dataclass instance
            title: Dialog window title
            parent: Parent widget

        Returns:
            Updated config dataclass on OK, or None on Cancel
        """
        dialog = QConfigUIDialog(config_ui_class, config, title, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.get_config()
        return None
