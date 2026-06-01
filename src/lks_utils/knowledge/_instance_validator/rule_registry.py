"""Rule constants for InstanceValidator internals."""
from __future__ import annotations

VALIDATION_STATUS_PROP = "__validation_status__"
VALIDATION_ERRORS_PROP = "__validation_errors__"
VALIDATION_STATUS_CANNOT_COMPILE = "cannot_compile"
TYPE_VERSION_PROP = "__type_version__"
PROPERTY_VERSIONS_PROP = "__property_versions__"
PROTOTYPE_ID_PROP = "__prototype_id__"
RESERVED_VALIDATION_PROP_NAMES = {
    VALIDATION_STATUS_PROP,
    VALIDATION_ERRORS_PROP,
    TYPE_VERSION_PROP,
    PROPERTY_VERSIONS_PROP,
    PROTOTYPE_ID_PROP,
}
