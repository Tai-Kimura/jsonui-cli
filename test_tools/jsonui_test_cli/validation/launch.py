"""Launch configuration validation (root-level 'launch' object)."""

from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import (
    VALID_LAUNCH_KEYS,
    VALID_PERMISSION_NAMES,
    VALID_PERMISSION_VALUES,
)


def validate_launch(launch, path: str, result: ValidationResult):
    """Validate a root-level launch configuration object."""
    if not isinstance(launch, dict):
        result.errors.append(ValidationMessage(
            path=path,
            message=f"'launch' must be an object, got: {type(launch).__name__}"
        ))
        return

    for key in launch.keys():
        if key not in VALID_LAUNCH_KEYS:
            result.warnings.append(ValidationMessage(
                path=path,
                message=f"Unknown launch key: {key}",
                level="warning"
            ))

    if "clearState" in launch and not isinstance(launch["clearState"], bool):
        result.errors.append(ValidationMessage(
            path=path,
            message=f"'clearState' must be a boolean, got: {type(launch['clearState']).__name__}"
        ))

    if "permissions" in launch:
        permissions = launch["permissions"]
        if not isinstance(permissions, dict):
            result.errors.append(ValidationMessage(
                path=f"{path}.permissions",
                message=f"'permissions' must be an object, got: {type(permissions).__name__}"
            ))
        else:
            for name, value in permissions.items():
                if name not in VALID_PERMISSION_NAMES:
                    result.errors.append(ValidationMessage(
                        path=f"{path}.permissions",
                        message=f"Unknown permission name: {name}. Must be one of: {VALID_PERMISSION_NAMES}"
                    ))
                if value not in VALID_PERMISSION_VALUES:
                    result.errors.append(ValidationMessage(
                        path=f"{path}.permissions.{name}",
                        message=f"Invalid permission value: {value}. Must be one of: {VALID_PERMISSION_VALUES}"
                    ))

    if "arguments" in launch:
        arguments = launch["arguments"]
        if not isinstance(arguments, dict):
            result.errors.append(ValidationMessage(
                path=f"{path}.arguments",
                message=f"'arguments' must be an object, got: {type(arguments).__name__}"
            ))
        else:
            for key, value in arguments.items():
                if not isinstance(value, (str, int, float, bool)):
                    result.errors.append(ValidationMessage(
                        path=f"{path}.arguments.{key}",
                        message=f"Launch argument value must be a primitive type (string, number, boolean), got: {type(value).__name__}"
                    ))
