"""Qt Job List Component - Job management with status indicators.

Provides a table-based job list with add/remove/toggle operations and status indicators.
Reusable for any job management UI (backups, scheduled tasks, batch processing, etc.).
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from typing import Any, Callable
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QAbstractItemView,
    QHeaderView,
)
from PySide6.QtCore import Signal

from lks_utils.gui_qt.widgets.data_table_widget import QDataTableWidget

@dataclass
class JobItem:
    """Single job item with metadata.

    Attributes:
        id: Unique identifier for the job
        columns: Dictionary of column_name → display_value
        enabled: Whether job is enabled
        metadata: Optional additional data (not displayed)
    """
    id: str
    columns: dict[str, str]
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

class QJobListComponent(QWidget):
    """Job list component with add/remove/toggle functionality.

    Features:
    - Table-based display with configurable columns
    - Multi-select support
    - Status indicators (emoji or text)
    - Enable/disable toggle
    - Add/remove operations
    - Selection callbacks

    Signals:
        job_added: Emitted when add button clicked (no parameters, consumer handles)
        job_removed: Emitted with list of removed job IDs
        job_toggled: Emitted with list of toggled job IDs
        selection_changed: Emitted with list of selected job IDs

    Example:
        # Create component with column definitions
        columns = ["Source", "Destination", "Type", "Last Backup", "Status"]
        job_list = QJobListComponent(columns=columns)

        # Connect signals
        job_list.job_added.connect(lambda: handle_add_job())
        job_list.job_removed.connect(lambda ids: handle_remove(ids))

        # Add jobs
        job = JobItem(
            id="job_001",
            columns={
                "Source": "/data/docs",
                "Destination": "/backup/docs",
                "Type": "archive",
                "Last Backup": "2026-01-14 10:30",
                "Status": "✓ OK"
            }
        )
        job_list.add_job(job)
    """

    # Signals
    job_added = Signal()
    job_removed = Signal(list)  # list[str] of job IDs
    job_toggled = Signal(list)  # list[str] of job IDs
    selection_changed = Signal(list)  # list[str] of job IDs

    def __init__(
        self,
        columns: list[str],
        show_add_button: bool = True,
        show_remove_button: bool = True,
        show_toggle_button: bool = True,
        parent: QWidget | None = None
    ):
        """Initialize component.

        Args:
            columns: List of column names (in display order)
            show_add_button: Whether to show Add button
            show_remove_button: Whether to show Remove button
            show_toggle_button: Whether to show Enable/Disable button
            parent: Parent widget
        """
        super().__init__(parent)

        self._columns = columns
        self._jobs: dict[str, JobItem] = {}  # id → JobItem
        self._show_add_btn = show_add_button
        self._show_remove_btn = show_remove_button
        self._show_toggle_btn = show_toggle_button

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Table widget with sorting and resizing
        # Note: editable=False for read-only job list
        # row_resize_mode=ResizeToContents for auto-height
        self._table = QDataTableWidget(
            columns=self._columns,
            sortable=True,
            show_row_numbers=False,
            selection_mode=QAbstractItemView.ExtendedSelection,
            editable=False,
            row_resize_mode=QHeaderView.ResizeToContents
        )

        # Connect selection signal
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self._table)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 5, 0, 0)

        if self._show_add_btn:
            self._add_btn = QPushButton("+ Add Job")
            self._add_btn.clicked.connect(self._on_add_clicked)
            btn_layout.addWidget(self._add_btn)

        if self._show_remove_btn:
            self._remove_btn = QPushButton("Remove Selected")
            self._remove_btn.clicked.connect(self._on_remove_clicked)
            self._remove_btn.setEnabled(False)
            btn_layout.addWidget(self._remove_btn)

        if self._show_toggle_btn:
            self._toggle_btn = QPushButton("Enable/Disable")
            self._toggle_btn.clicked.connect(self._on_toggle_clicked)
            self._toggle_btn.setEnabled(False)
            btn_layout.addWidget(self._toggle_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_selection_changed(self):
        """Handle selection change."""
        selected_ids = self.get_selected_job_ids()
        has_selection = len(selected_ids) > 0

        if self._show_remove_btn:
            self._remove_btn.setEnabled(has_selection)
        if self._show_toggle_btn:
            self._toggle_btn.setEnabled(has_selection)

        self.selection_changed.emit(selected_ids)

    def _on_add_clicked(self):
        """Handle add button click."""
        self.job_added.emit()

    def _on_remove_clicked(self):
        """Handle remove button click."""
        selected_ids = self.get_selected_job_ids()
        if selected_ids:
            self.job_removed.emit(selected_ids)

    def _on_toggle_clicked(self):
        """Handle toggle button click."""
        selected_ids = self.get_selected_job_ids()
        if selected_ids:
            self.job_toggled.emit(selected_ids)

    def add_job(self, job: JobItem):
        """Add a job to the list.

        Args:
            job: JobItem to add
        """
        # Store job
        self._jobs[job.id] = job

        # Prepare row data
        row_data = [job.columns.get(col_name, "")
                    for col_name in self._columns]

        # Add to table with job ID as user data
        self._table.add_row(row_data, user_data=job.id, editable=False)

    def remove_job(self, job_id: str):
        """Remove a job from the list.

        Args:
            job_id: ID of job to remove
        """
        if job_id not in self._jobs:
            return

        # Find row with this ID
        for row in range(self._table.rowCount()):
            user_data = self._table.get_row_user_data(row)
            if user_data == job_id:
                self._table.remove_row(row)
                del self._jobs[job_id]
                break

    def remove_selected_jobs(self):
        """Remove all selected jobs."""
        selected_ids = self.get_selected_job_ids()
        for job_id in selected_ids:
            self.remove_job(job_id)

    def update_job(self, job: JobItem):
        """Update an existing job's display.

        Args:
            job: Updated JobItem
        """
        # Find row
        for row in range(self._table.rowCount()):
            user_data = self._table.get_row_user_data(row)
            if user_data == job.id:
                # Update columns
                row_data = [job.columns.get(col_name, "")
                            for col_name in self._columns]
                self._table.update_row(row, row_data)

                # Update stored job
                self._jobs[job.id] = job
                break

    def clear(self):
        """Clear all jobs from the list."""
        self._table.clear_data()
        self._jobs.clear()

    def get_job(self, job_id: str) -> JobItem | None:
        """Get a job by ID.

        Args:
            job_id: Job ID

        Returns:
            JobItem if found, None otherwise
        """
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[JobItem]:
        """Get all jobs.

        Returns:
            List of all JobItems
        """
        return list(self._jobs.values())

    def get_selected_job_ids(self) -> list[str]:
        """Get IDs of selected jobs.

        Returns:
            List of job IDs
        """
        return self._table.get_selected_user_data()

    def get_selected_jobs(self) -> list[JobItem]:
        """Get selected jobs.

        Returns:
            List of selected JobItems
        """
        job_ids = self.get_selected_job_ids()
        return [self._jobs[job_id] for job_id in job_ids if job_id in self._jobs]

    def set_selected_job_ids(self, job_ids: list[str]):
        """Set selected jobs by ID.

        Args:
            job_ids: List of job IDs to select
        """
        self._table.clearSelection()

        for row in range(self._table.rowCount()):
            user_data = self._table.get_row_user_data(row)
            if user_data in job_ids:
                self._table.selectRow(row)

    def get_job_count(self) -> int:
        """Get total number of jobs.

        Returns:
            Job count
        """
        return len(self._jobs)

    # State persistence
    def to_dict(self) -> dict[str, Any]:
        """Export state for persistence.

        Returns:
            State dictionary with job data
        """
        return {
            "jobs": [
                {
                    "id": job.id,
                    "columns": job.columns,
                    "enabled": job.enabled,
                    "metadata": job.metadata,
                }
                for job in self._jobs.values()
            ],
            "selected_ids": self.get_selected_job_ids(),
        }

    def from_dict(self, state: dict[str, Any]):
        """Restore state from dictionary.

        Args:
            state: State dictionary from to_dict()
        """
        self.clear()

        # Restore jobs
        for job_data in state.get("jobs", []):
            job = JobItem(
                id=job_data["id"],
                columns=job_data["columns"],
                enabled=job_data.get("enabled", True),
                metadata=job_data.get("metadata", {}),
            )
            self.add_job(job)

        # Restore selection
        selected_ids = state.get("selected_ids", [])
        if selected_ids:
            self.set_selected_job_ids(selected_ids)
