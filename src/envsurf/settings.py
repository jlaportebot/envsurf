"""Typed, validated settings from environment variables and .env files.

This module provides EnvSettings — a declarative way to define typed config
from env vars, .env files, and .env.example with automatic validation,
type coercion, schema generation, and observable access.
"""

from __future__ import annotations

import enum
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    FrozenSet,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from .parser import EnvFile, parse_env

T = TypeVar("T")

# ── Exceptions ──────────────────────────────────────────────────────────────

class SettingsError(Exception):
    """Base exception for settings errors."""


class ValidationError(SettingsError):
    """Raised when a value fails validation."""

    def __init__(self, key: str, value: Any, expected_type: type, detail: str = "") -> None:
        self.key = key
        self.value = value
        self.expected_type = expected_type
        self.detail = detail
        msg = f"Invalid value for {key!r}: expected {expected_type.__name__}"
        if detail:
            msg += f" ({detail})"
        msg += f", got {value!r}"
        super().__init__(msg)


class MissingRequiredError(SettingsError):
    """Raised when a required variable is not set."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Required environment variable {key!r} is not set")


# ── Field descriptor ────────────────────────────────────────────────────────

@dataclass
class EnvField:
    """Describes a single environment variable field."""

    name: str
    type: type
    required: bool = True
    default: Any = None
    description: str = ""
    alias: str = ""  # alternative env var name
    choices: Optional[Sequence[str]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None  # regex pattern the value must match
    sensitive: bool = False  # mark as secret in schema
    separator: str = ","  # separator for list/set types

    @property
    def env_key(self) -> str:
        """The environment variable name to look up."""
        return self.alias or self.name

    def to_schema_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable schema dict."""
        schema: Dict[str, Any] = {
            "name": self.name,
            "env_key": self.env_key,
            "type": _type_name(self.type),
            "required": self.required,
        }
        if not self.required and self.default is not None:
            schema["default"] = self.default
        if self.description:
            schema["description"] = self.description
        if self.choices:
            schema["choices"] = list(self.choices)
        if self.min_value is not None:
            schema["min"] = self.min_value
        if self.max_value is not None:
            schema["max"] = self.max_value
        if self.pattern:
            schema["pattern"] = self.pattern
        if self.sensitive:
            schema["sensitive"] = True
        return schema


# ── Validation functions ─────────────────────────────────────────────────────

def _is_optional_type(tp: type) -> bool:
    """Check if a type is Optional[X] (i.e. Union[X, None])."""
    origin = get_origin(tp)
    if origin is Union:
        return type(None) in get_args(tp)
    return False


def _unwrap_optional(tp: type) -> type:
    """Unwrap Optional[X] to get X."""
    args = [a for a in get_args(tp) if a is not type(None)]
    return args[0] if args else tp


def _type_name(tp: type) -> str:
    """Get a human-readable name for a type."""
    if _is_optional_type(tp):
        return f"Optional[{_type_name(_unwrap_optional(tp))}]"
    origin = get_origin(tp)
    if origin is list or origin is List:
        args = get_args(tp)
        if args:
            return f"List[{_type_name(args[0])}]"
        return "List"
    if origin is set or origin is Set:
        args = get_args(tp)
        if args:
            return f"Set[{_type_name(args[0])}]"
        return "Set"
    if origin is frozenset or origin is FrozenSet:
        args = get_args(tp)
        if args:
            return f"FrozenSet[{_type_name(args[0])}]"
        return "FrozenSet"
    if origin is tuple or origin is Tuple:
        args = get_args(tp)
        if args:
            return f"Tuple[{', '.join(_type_name(a) for a in args)}]"
        return "Tuple"
    if origin is dict or origin is Dict:
        args = get_args(tp)
        if args:
            return f"Dict[{_type_name(args[0])}, {_type_name(args[1])}]"
        return "Dict"
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp.__name__
    if hasattr(tp, "__name__"):
        return tp.__name__
    return str(tp)


def _coerce_value(raw: str, target_type: type, field: EnvField) -> Any:
    """Coerce a raw string value to the target type.

    Raises ValidationError if coercion fails.
    """
    # Handle Optional types
    actual_type = target_type
    if _is_optional_type(target_type):
        actual_type = _unwrap_optional(target_type)

    # Strip whitespace for non-string types
    stripped = raw.strip() if actual_type is not str else raw

    # Handle None / empty for optional types
    if not stripped:
        if _is_optional_type(target_type):
            return None
        if actual_type == str:
            return stripped
        raise ValidationError(field.env_key, raw, actual_type, "empty value for required field")

    # Enum types
    origin = get_origin(actual_type)
    if isinstance(actual_type, type) and issubclass(actual_type, Enum):
        try:
            return actual_type(stripped)
        except ValueError:
            valid = [e.value for e in actual_type]
            raise ValidationError(field.env_key, raw, actual_type, f"must be one of {valid}")

    # List types
    if origin is list or origin is List:
        args = get_args(actual_type)
        item_type = args[0] if args else str
        parts = [p.strip() for p in stripped.split(field.separator) if p.strip()]
        return [_coerce_single(p, item_type, field) for p in parts]

    # Set types
    if origin is set or origin is Set:
        args = get_args(actual_type)
        item_type = args[0] if args else str
        parts = [p.strip() for p in stripped.split(field.separator) if p.strip()]
        return {_coerce_single(p, item_type, field) for p in parts}

    # FrozenSet types
    if origin is frozenset or origin is FrozenSet:
        args = get_args(actual_type)
        item_type = args[0] if args else str
        parts = [p.strip() for p in stripped.split(field.separator) if p.strip()]
        return frozenset(_coerce_single(p, item_type, field) for p in parts)

    # Tuple types
    if origin is tuple or origin is Tuple:
        args = get_args(actual_type)
        parts = [p.strip() for p in stripped.split(field.separator)]
        if args and len(args) > 1 and args[-1] is not Ellipsis:
            # Fixed-length tuple
            if len(parts) != len(args):
                raise ValidationError(
                    field.env_key, raw, actual_type,
                    f"expected {len(args)} items, got {len(parts)}",
                )
            return tuple(_coerce_single(p, t, field) for p, t in zip(parts, args))
        # Variable-length tuple (Tuple[X, ...])
        item_type = args[0] if args else str
        return tuple(_coerce_single(p, item_type, field) for p in parts)

    # Dict types (KEY=VAL,KEY2=VAL2)
    if origin is dict or origin is Dict:
        args = get_args(actual_type)
        key_type = args[0] if args else str
        val_type = args[1] if len(args) > 1 else str
        result = {}
        for part in stripped.split(field.separator):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[_coerce_single(k.strip(), key_type, field)] = _coerce_single(v.strip(), val_type, field)
            else:
                raise ValidationError(
                    field.env_key, raw, actual_type,
                    f"dict items must be KEY=VALUE, got {part!r}",
                )
        return result

    # Bool (before int since bool is a subclass of int)
    if actual_type is bool:
        return stripped.lower() in ("true", "1", "yes", "on", "t")

    # Int
    if actual_type is int:
        try:
            # Support hex and binary
            if stripped.startswith("0x") or stripped.startswith("0X"):
                return int(stripped, 16)
            if stripped.startswith("0b") or stripped.startswith("0B"):
                return int(stripped, 2)
            return int(stripped)
        except ValueError:
            raise ValidationError(field.env_key, raw, int, "not a valid integer")

    # Float
    if actual_type is float:
        try:
            # Support special values
            if stripped.lower() in ("inf", "+inf", "infinity"):
                return float("inf")
            if stripped.lower() in ("-inf", "-infinity"):
                return float("-inf")
            if stripped.lower() in ("nan",):
                return float("nan")
            return float(stripped)
        except ValueError:
            raise ValidationError(field.env_key, raw, float, "not a valid float")

    # Path
    if actual_type is Path:
        return Path(stripped)

    # String
    if actual_type is str:
        return stripped

    # Fallback: try constructor
    try:
        return actual_type(stripped)
    except (ValueError, TypeError) as exc:
        raise ValidationError(field.env_key, raw, actual_type, str(exc))


def _coerce_single(raw: str, target_type: type, env_field: EnvField) -> Any:
    """Coerce a single value (used for items in containers)."""
    # Create a temporary field for error reporting
    tmp = EnvField(name=env_field.name, type=target_type, required=True, separator=env_field.separator)
    return _coerce_value(raw, target_type, tmp)


def _validate_field(value: Any, field: EnvField) -> None:
    """Validate a coerced value against field constraints."""
    if value is None:
        if field.required and not _is_optional_type(field.type):
            raise MissingRequiredError(field.env_key)
        return

    # Choices
    if field.choices is not None:
        str_val = str(value) if not isinstance(value, str) else value
        if str_val not in field.choices:
            raise ValidationError(
                field.env_key, value, field.type,
                f"must be one of {list(field.choices)}",
            )

    # Min/Max for numeric types
    if field.min_value is not None and isinstance(value, (int, float)):
        if value < field.min_value:
            raise ValidationError(
                field.env_key, value, field.type,
                f"must be >= {field.min_value}",
            )
    if field.max_value is not None and isinstance(value, (int, float)):
        if value > field.max_value:
            raise ValidationError(
                field.env_key, value, field.type,
                f"must be <= {field.max_value}",
            )

    # Regex pattern
    if field.pattern is not None and isinstance(value, str):
        if not re.match(field.pattern, value):
            raise ValidationError(
                field.env_key, value, field.type,
                f"must match pattern {field.pattern!r}",
            )


# ── Settings class ──────────────────────────────────────────────────────────

class EnvSettings:
    """Base class for typed, validated environment variable settings.

    Define your settings by subclassing and adding class-level EnvField
    descriptors:

        class AppConfig(EnvSettings):
            DEBUG = EnvField(name="DEBUG", type=bool, default=False, description="Enable debug mode")
            PORT = EnvField(name="PORT", type=int, default=8000, min_value=1, max_value=65535)
            DATABASE_URL = EnvField(name="DATABASE_URL", type=str, required=True, sensitive=True)

        config = AppConfig.load()  # reads from env + .env file
        print(config.DEBUG)  # True
        print(config.PORT)   # 8000

    Supports:
    - Type coercion (str, int, float, bool, Path, Enum, List, Set, Tuple, Dict)
    - Required/optional with defaults
    - Validation (choices, min/max, regex pattern)
    - Env var aliases
    - Sensitive field masking
    - Schema generation
    - Multiple sources (env vars, .env files, dict)
    """

    _fields: ClassVar[Dict[str, EnvField]] = {}
    _values: Dict[str, Any] = {}
    _source_info: Dict[str, str] = {}  # key -> source description

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Collect EnvField descriptors from the class
        fields: Dict[str, EnvField] = {}
        for name in list(cls.__dict__):
            obj = cls.__dict__[name]
            if isinstance(obj, EnvField):
                fields[name] = obj
                # Replace the EnvField class attribute with a property
                # so attribute access returns the resolved value, not the descriptor
                _name = name  # capture in closure
                prop = property(lambda self, __name=_name: self._values.get(__name))
                setattr(cls, name, prop)
        cls._fields = fields

    def __init__(self, values: Dict[str, Any], source_info: Optional[Dict[str, str]] = None) -> None:
        self._values = values
        self._source_info = source_info or {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in type(self)._fields:
            return self._values.get(name)
        raise AttributeError(f"{type(self).__name__!r} has no setting {name!r}")

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        fields = []
        for name, f in type(self)._fields.items():
            val = self._values.get(name)
            display = "***" if f.sensitive and val is not None else repr(val)
            fields.append(f"{name}={display}")
        return f"{cls_name}({', '.join(fields)})"

    # ── Load methods ─────────────────────────────────────────────────────

    @classmethod
    def load(
        cls,
        *,
        env_file: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        strict: bool = False,
        allow_extra: bool = True,
    ) -> "EnvSettings":
        """Load settings from environment variables and optional .env file.

        Resolution order (later sources override earlier):
        1. Defaults from field definitions
        2. Values from .env file (if provided)
        3. Values from os.environ
        4. Values from explicit env dict (if provided)

        Args:
            env_file: Path to a .env file to load (optional).
            env: Explicit dict of env var overrides (optional).
            strict: If True, raise SettingsError for unknown env vars.
            allow_extra: If False and strict=True, error on vars not in schema.

        Returns:
            An instance of the settings class with typed values.

        Raises:
            MissingRequiredError: If a required field has no value.
            ValidationError: If a value can't be coerced or fails constraints.
            SettingsError: If strict mode and unknown vars are found.
        """
        # Build lookup of env_key -> field name
        env_key_to_field: Dict[str, Tuple[str, EnvField]] = {}
        for attr_name, f in cls._fields.items():
            env_key_to_field[f.env_key] = (attr_name, f)

        # Collect raw values from all sources
        raw_values: Dict[str, str] = {}
        source_info: Dict[str, str] = {}

        # 1. Defaults
        for attr_name, f in cls._fields.items():
            if f.default is not None:
                default_val = f.default
                # Use .value for enum defaults to get the string form
                if isinstance(default_val, enum.Enum):
                    default_val = default_val.value
                raw_values[f.env_key] = str(default_val)
                source_info[f.env_key] = "default"

        # 2. .env file
        if env_file is not None and env_file.exists():
            parsed = parse_env(env_file)
            for entry in parsed.entries:
                raw_values[entry.key] = entry.raw_value
                source_info[entry.key] = str(env_file)

        # 3. os.environ
        for key, value in os.environ.items():
            if key in env_key_to_field or key in {f.env_key for _, f in env_key_to_field.values()}:
                raw_values[key] = value
                source_info[key] = "environment"

        # 4. Explicit overrides
        if env is not None:
            for key, value in env.items():
                raw_values[key] = value
                source_info[key] = "explicit"

        # Coerce and validate
        return cls._build_instance(raw_values, source_info, strict=strict)

    @classmethod
    def _build_instance(
        cls,
        raw_values: Dict[str, str],
        source_info: Dict[str, str],
        *,
        strict: bool = False,
    ) -> "EnvSettings":
        """Coerce raw string values, validate, and construct an instance."""
        # Build lookup for strict mode checking
        env_key_to_field: Dict[str, Tuple[str, EnvField]] = {}
        for attr_name, f in cls._fields.items():
            env_key_to_field[f.env_key] = (attr_name, f)

        # Strict mode: check for unknown variables
        if strict:
            known_keys = {f.env_key for _, f in env_key_to_field.values()}
            unknown = set(raw_values.keys()) - known_keys
            if unknown:
                raise SettingsError(f"Unknown environment variables: {sorted(unknown)}")

        typed_values: Dict[str, Any] = {}
        for attr_name, f in cls._fields.items():
            raw = raw_values.get(f.env_key)

            if raw is None:
                if f.required and not _is_optional_type(f.type):
                    raise MissingRequiredError(f.env_key)
                if _is_optional_type(f.type):
                    typed_values[attr_name] = None
                elif f.default is not None:
                    typed_values[attr_name] = f.default
                else:
                    typed_values[attr_name] = None
            else:
                value = _coerce_value(raw, f.type, f)
                _validate_field(value, f)
                typed_values[attr_name] = value

        return cls(typed_values, source_info)

    @classmethod
    def from_dict(cls, env: Dict[str, str], *, strict: bool = False) -> "EnvSettings":
        """Create settings from an explicit dict only.

        Unlike ``load``, this does NOT read from os.environ or .env files.
        Use this for testing or when you want full control over values.

        Args:
            env: Dict mapping env var names to string values.
            strict: If True, raise SettingsError for unknown env vars.

        Returns:
            An instance of the settings class with typed values.
        """
        # Start with defaults
        raw_values: Dict[str, str] = {}
        source_info: Dict[str, str] = {}

        for attr_name, f in cls._fields.items():
            if f.default is not None:
                default_val = f.default
                if isinstance(default_val, enum.Enum):
                    default_val = default_val.value
                raw_values[f.env_key] = str(default_val)
                source_info[f.env_key] = "default"

        # Apply explicit overrides (ONLY from the dict, not os.environ)
        for key, value in env.items():
            raw_values[key] = value
            source_info[key] = "explicit"

        # Coerce and validate
        return cls._build_instance(raw_values, source_info, strict=strict)

    @classmethod
    def from_env_file(cls, path: Path, *, strict: bool = False) -> "EnvSettings":
        """Load settings from an .env file only (no os.environ).

        Args:
            path: Path to the .env file.
            strict: If True, raise on unknown keys.

        Returns:
            An instance of the settings class with typed values.
        """
        # Build a dict from the file
        parsed = parse_env(path)
        env_dict = parsed.as_dict()
        return cls.load(env=env_dict, strict=strict)

    # ── Schema ───────────────────────────────────────────────────────────

    @classmethod
    def schema(cls) -> Dict[str, Any]:
        """Generate a JSON-serializable schema describing all fields.

        Returns:
            Dict with 'name' and 'fields' keys.
        """
        return {
            "name": cls.__name__,
            "fields": [f.to_schema_dict() for f in cls._fields.values()],
        }

    @classmethod
    def schema_json(cls, *, indent: int = 2) -> str:
        """Generate a JSON string schema."""
        return json.dumps(cls.schema(), indent=indent)

    @classmethod
    def generate_env_example(cls, *, include_comments: bool = True) -> str:
        """Generate an .env.example file from the schema.

        Args:
            include_comments: Include descriptions and type info as comments.

        Returns:
            String content for an .env.example file.
        """
        lines: List[str] = []
        if include_comments:
            lines.append(f"# Settings schema for {cls.__name__}")
            lines.append(f"# Generated by envsurf {__import__('envsurf', fromlist=['__version__']).__version__}")
            lines.append("")

        for f in cls._fields.values():
            if include_comments and f.description:
                lines.append(f"# {f.description}")
            if include_comments:
                type_str = _type_name(f.type)
                constraints = []
                if f.required:
                    constraints.append("required")
                else:
                    constraints.append("optional")
                if f.default is not None:
                    constraints.append(f"default: {f.default}")
                if f.choices:
                    constraints.append(f"choices: {list(f.choices)}")
                if f.min_value is not None:
                    constraints.append(f"min: {f.min_value}")
                if f.max_value is not None:
                    constraints.append(f"max: {f.max_value}")
                if f.pattern:
                    constraints.append(f"pattern: {f.pattern}")
                if f.sensitive:
                    constraints.append("sensitive")
                lines.append(f"# Type: {type_str}, {', '.join(constraints)}")

            if f.default is not None:
                default_str = str(f.default)
                if f.sensitive:
                    default_str = "changeme"
                lines.append(f"{f.env_key}={default_str}")
            elif f.required:
                lines.append(f"{f.env_key}=")
            else:
                lines.append(f"# {f.env_key}=")

            if include_comments:
                lines.append("")

        return "\n".join(lines)

    # ── Access helpers ───────────────────────────────────────────────────

    def as_dict(self, *, mask_sensitive: bool = True) -> Dict[str, Any]:
        """Return all values as a dict.

        Args:
            mask_sensitive: Replace sensitive values with '***'.
        """
        result = {}
        for name, f in type(self)._fields.items():
            val = self._values.get(name)
            if mask_sensitive and f.sensitive and val is not None:
                result[name] = "***"
            else:
                result[name] = val
        return result

    def source_of(self, name: str) -> Optional[str]:
        """Return where a setting's value came from (e.g., 'environment', '.env', 'default')."""
        f = type(self)._fields.get(name)
        if f is None:
            return None
        return self._source_info.get(f.env_key)

    def is_set(self, name: str) -> bool:
        """Check if a setting has a value (not None)."""
        return self._values.get(name) is not None

    def missing_required(self) -> List[str]:
        """Return list of required field names that have no value."""
        missing = []
        for name, f in type(self)._fields.items():
            if f.required and not _is_optional_type(f.type) and self._values.get(name) is None:
                missing.append(name)
        return missing

    def errors(self) -> List[str]:
        """Validate all fields and return a list of error messages (empty if valid)."""
        errs: List[str] = []
        for name, f in type(self)._fields.items():
            val = self._values.get(name)
            try:
                _validate_field(val, f)
            except (ValidationError, MissingRequiredError) as exc:
                errs.append(str(exc))
        return errs

    def is_valid(self) -> bool:
        """Check if all field values pass validation."""
        return len(self.errors()) == 0
