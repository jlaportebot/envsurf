"""Tests for envsurf settings module."""

import enum
import textwrap
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import pytest

from envsurf.settings import (
    EnvField,
    EnvSettings,
    MissingRequiredError,
    SettingsError,
    ValidationError,
    _coerce_value,
    _type_name,
    _validate_field,
)


# ── Test enums ──────────────────────────────────────────────────────────────

class LogLevel(enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Environment(enum.Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ── Test settings classes ───────────────────────────────────────────────────

class DatabaseConfig(EnvSettings):
    HOST = EnvField(name="DB_HOST", type=str, required=True, description="Database host")
    PORT = EnvField(name="DB_PORT", type=int, default=5432, required=False, min_value=1, max_value=65535, description="Database port")
    NAME = EnvField(name="DB_NAME", type=str, required=True, description="Database name")
    URL = EnvField(name="DATABASE_URL", type=str, required=False, sensitive=True, description="Full connection URL")
    TIMEOUT = EnvField(name="DB_TIMEOUT", type=float, default=30.0, required=False, min_value=0.1, description="Connection timeout in seconds")


class AppConfig(EnvSettings):
    DEBUG = EnvField(name="DEBUG", type=bool, default=False, required=False, description="Enable debug mode")
    PORT = EnvField(name="PORT", type=int, default=8000, required=False, min_value=1, max_value=65535, description="Application port")
    LOG_LEVEL = EnvField(name="LOG_LEVEL", type=LogLevel, default=LogLevel.INFO, required=False, description="Logging level")
    ALLOWED_HOSTS = EnvField(name="ALLOWED_HOSTS", type=List[str], required=False, separator=",", description="Comma-separated list of allowed hosts")
    API_KEYS = EnvField(name="API_KEYS", type=Set[str], required=False, separator=",", sensitive=True, description="Comma-separated API keys")
    ENV = EnvField(name="APP_ENV", type=Environment, required=True, description="Deployment environment")
    SECRET_KEY = EnvField(name="SECRET_KEY", type=str, required=True, sensitive=True, description="Application secret key", pattern=r"^.{16,}$")
    WORKERS = EnvField(name="WORKERS", type=int, default=4, required=False, choices=["1", "2", "4", "8"], description="Number of workers")


class SimpleConfig(EnvSettings):
    NAME = EnvField(name="APP_NAME", type=str, required=True)
    DEBUG = EnvField(name="DEBUG", type=bool, default=False, required=False)


class OptionalConfig(EnvSettings):
    HOST = EnvField(name="HOST", type=str, required=True)
    PORT = EnvField(name="PORT", type=int, required=False, default=8080)
    API_KEY = EnvField(name="API_KEY", type=str, required=False)  # optional, no default


# ── Coercion tests ──────────────────────────────────────────────────────────

class TestCoerceValue:
    def test_str(self) -> None:
        f = EnvField(name="TEST", type=str, required=True)
        assert _coerce_value("hello", str, f) == "hello"

    def test_int(self) -> None:
        f = EnvField(name="TEST", type=int, required=True)
        assert _coerce_value("42", int, f) == 42

    def test_int_hex(self) -> None:
        f = EnvField(name="TEST", type=int, required=True)
        assert _coerce_value("0xFF", int, f) == 255

    def test_int_binary(self) -> None:
        f = EnvField(name="TEST", type=int, required=True)
        assert _coerce_value("0b1010", int, f) == 10

    def test_int_invalid(self) -> None:
        f = EnvField(name="TEST", type=int, required=True)
        with pytest.raises(ValidationError):
            _coerce_value("not_a_number", int, f)

    def test_float(self) -> None:
        f = EnvField(name="TEST", type=float, required=True)
        assert _coerce_value("3.14", float, f) == 3.14

    def test_float_inf(self) -> None:
        f = EnvField(name="TEST", type=float, required=True)
        assert _coerce_value("inf", float, f) == float("inf")

    def test_float_negative_inf(self) -> None:
        f = EnvField(name="TEST", type=float, required=True)
        assert _coerce_value("-inf", float, f) == float("-inf")

    def test_float_invalid(self) -> None:
        f = EnvField(name="TEST", type=float, required=True)
        with pytest.raises(ValidationError):
            _coerce_value("abc", float, f)

    def test_bool_true_variants(self) -> None:
        f = EnvField(name="TEST", type=bool, required=True)
        for val in ("true", "1", "yes", "on", "t", "True", "TRUE", "YES"):
            assert _coerce_value(val, bool, f) is True

    def test_bool_false(self) -> None:
        f = EnvField(name="TEST", type=bool, required=True)
        assert _coerce_value("false", bool, f) is False
        assert _coerce_value("0", bool, f) is False
        assert _coerce_value("no", bool, f) is False

    def test_path(self) -> None:
        f = EnvField(name="TEST", type=Path, required=True)
        result = _coerce_value("/tmp/test", Path, f)
        assert isinstance(result, Path)
        assert str(result) == "/tmp/test"

    def test_list_str(self) -> None:
        f = EnvField(name="TEST", type=List[str], required=True, separator=",")
        assert _coerce_value("a,b,c", List[str], f) == ["a", "b", "c"]

    def test_list_int(self) -> None:
        f = EnvField(name="TEST", type=List[int], required=True, separator=",")
        assert _coerce_value("1,2,3", List[int], f) == [1, 2, 3]

    def test_list_custom_separator(self) -> None:
        f = EnvField(name="TEST", type=List[str], required=True, separator="|")
        assert _coerce_value("a|b|c", List[str], f) == ["a", "b", "c"]

    def test_set_str(self) -> None:
        f = EnvField(name="TEST", type=Set[str], required=True, separator=",")
        result = _coerce_value("a,b,a", Set[str], f)
        assert result == {"a", "b"}

    def test_set_int(self) -> None:
        f = EnvField(name="TEST", type=Set[int], required=True, separator=",")
        result = _coerce_value("1,2,3", Set[int], f)
        assert result == {1, 2, 3}

    def test_frozenset_str(self) -> None:
        f = EnvField(name="TEST", type=FrozenSet[str], required=True, separator=",")
        result = _coerce_value("x,y", FrozenSet[str], f)
        assert result == frozenset({"x", "y"})

    def test_tuple_fixed(self) -> None:
        f = EnvField(name="TEST", type=Tuple[str, int], required=True, separator=",")
        result = _coerce_value("hello,42", Tuple[str, int], f)
        assert result == ("hello", 42)

    def test_tuple_fixed_wrong_length(self) -> None:
        f = EnvField(name="TEST", type=Tuple[str, int], required=True, separator=",")
        with pytest.raises(ValidationError):
            _coerce_value("hello", Tuple[str, int], f)

    def test_tuple_variable(self) -> None:
        f = EnvField(name="TEST", type=Tuple[int, ...], required=True, separator=",")
        result = _coerce_value("1,2,3", Tuple[int, ...], f)
        assert result == (1, 2, 3)

    def test_dict_str_str(self) -> None:
        f = EnvField(name="TEST", type=Dict[str, str], required=True, separator=",")
        result = _coerce_value("key1=val1,key2=val2", Dict[str, str], f)
        assert result == {"key1": "val1", "key2": "val2"}

    def test_dict_str_int(self) -> None:
        f = EnvField(name="TEST", type=Dict[str, int], required=True, separator=",")
        result = _coerce_value("a=1,b=2", Dict[str, int], f)
        assert result == {"a": 1, "b": 2}

    def test_dict_invalid_format(self) -> None:
        f = EnvField(name="TEST", type=Dict[str, str], required=True, separator=",")
        with pytest.raises(ValidationError):
            _coerce_value("not_kv_pair", Dict[str, str], f)

    def test_enum(self) -> None:
        f = EnvField(name="TEST", type=LogLevel, required=True)
        result = _coerce_value("debug", LogLevel, f)
        assert result == LogLevel.DEBUG

    def test_enum_invalid(self) -> None:
        f = EnvField(name="TEST", type=LogLevel, required=True)
        with pytest.raises(ValidationError):
            _coerce_value("extreme", LogLevel, f)

    def test_optional_type_none(self) -> None:
        f = EnvField(name="TEST", type=Optional[str], required=False)
        result = _coerce_value("", Optional[str], f)
        assert result is None

    def test_optional_type_with_value(self) -> None:
        f = EnvField(name="TEST", type=Optional[int], required=False)
        result = _coerce_value("42", Optional[int], f)
        assert result == 42

    def test_whitespace_stripping(self) -> None:
        f = EnvField(name="TEST", type=int, required=True)
        assert _coerce_value("  42  ", int, f) == 42

    def test_whitespace_preserved_for_str(self) -> None:
        f = EnvField(name="TEST", type=str, required=True)
        assert _coerce_value("  hello  ", str, f) == "  hello  "


# ── Validation tests ────────────────────────────────────────────────────────

class TestValidateField:
    def test_choices_valid(self) -> None:
        f = EnvField(name="TEST", type=int, required=True, choices=["1", "2", "4"])
        _validate_field(1, f)  # Should not raise

    def test_choices_invalid(self) -> None:
        f = EnvField(name="TEST", type=int, required=True, choices=["1", "2", "4"])
        with pytest.raises(ValidationError):
            _validate_field(8, f)

    def test_min_value(self) -> None:
        f = EnvField(name="TEST", type=int, required=True, min_value=1)
        _validate_field(5, f)  # Should not raise
        with pytest.raises(ValidationError):
            _validate_field(0, f)

    def test_max_value(self) -> None:
        f = EnvField(name="TEST", type=int, required=True, max_value=100)
        _validate_field(50, f)  # Should not raise
        with pytest.raises(ValidationError):
            _validate_field(101, f)

    def test_min_max_range(self) -> None:
        f = EnvField(name="TEST", type=int, required=True, min_value=1, max_value=65535)
        _validate_field(80, f)  # Should not raise
        with pytest.raises(ValidationError):
            _validate_field(0, f)
        with pytest.raises(ValidationError):
            _validate_field(70000, f)

    def test_pattern_match(self) -> None:
        f = EnvField(name="TEST", type=str, required=True, pattern=r"^.{16,}$")
        _validate_field("a" * 16, f)  # Should not raise

    def test_pattern_no_match(self) -> None:
        f = EnvField(name="TEST", type=str, required=True, pattern=r"^.{16,}$")
        with pytest.raises(ValidationError):
            _validate_field("too_short", f)

    def test_none_required_raises(self) -> None:
        f = EnvField(name="TEST", type=str, required=True)
        with pytest.raises(MissingRequiredError):
            _validate_field(None, f)

    def test_none_optional_ok(self) -> None:
        f = EnvField(name="TEST", type=Optional[str], required=False)
        _validate_field(None, f)  # Should not raise


# ── Type name tests ─────────────────────────────────────────────────────────

class TestTypeName:
    def test_basic_types(self) -> None:
        assert _type_name(str) == "str"
        assert _type_name(int) == "int"
        assert _type_name(float) == "float"
        assert _type_name(bool) == "bool"

    def test_optional_type(self) -> None:
        assert _type_name(Optional[str]) == "Optional[str]"
        assert _type_name(Optional[int]) == "Optional[int]"

    def test_list_type(self) -> None:
        assert _type_name(List[str]) == "List[str]"
        assert _type_name(List[int]) == "List[int]"

    def test_set_type(self) -> None:
        assert _type_name(Set[str]) == "Set[str]"

    def test_dict_type(self) -> None:
        assert _type_name(Dict[str, int]) == "Dict[str, int]"

    def test_enum_type(self) -> None:
        assert _type_name(LogLevel) == "LogLevel"


# ── Settings loading tests ──────────────────────────────────────────────────

class TestEnvSettingsLoad:
    def test_from_dict_basic(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "myapp", "DEBUG": "true"})
        assert config.NAME == "myapp"
        assert config.DEBUG is True

    def test_from_dict_defaults(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "myapp"})
        assert config.NAME == "myapp"
        assert config.DEBUG is False

    def test_from_dict_missing_required(self) -> None:
        with pytest.raises(MissingRequiredError):
            SimpleConfig.from_dict({})

    def test_from_dict_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseConfig.from_dict({
                "DB_HOST": "localhost",
                "DB_NAME": "mydb",
                "DB_PORT": "99999",  # exceeds max_value 65535
            })

    def test_from_dict_float(self) -> None:
        config = DatabaseConfig.from_dict({
            "DB_HOST": "localhost",
            "DB_NAME": "mydb",
            "DB_TIMEOUT": "60.5",
        })
        assert config.TIMEOUT == 60.5

    def test_from_dict_with_enum(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a" * 20,
        })
        assert config.ENV == Environment.PRODUCTION

    def test_from_dict_with_list(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "development",
            "SECRET_KEY": "x" * 20,
            "ALLOWED_HOSTS": "localhost,127.0.0.1,example.com",
        })
        assert config.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "example.com"]

    def test_from_dict_with_set(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "staging",
            "SECRET_KEY": "y" * 20,
            "API_KEYS": "key1,key2,key3",
        })
        assert config.API_KEYS == {"key1", "key2", "key3"}

    def test_from_dict_alias(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "development",
            "SECRET_KEY": "z" * 20,
        })
        assert config.ENV == Environment.DEVELOPMENT

    def test_from_dict_pattern_validation(self) -> None:
        # Valid: 16+ chars
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a" * 20,
        })
        assert config.SECRET_KEY == "a" * 20

        # Invalid: too short
        with pytest.raises(ValidationError):
            AppConfig.from_dict({
                "APP_ENV": "production",
                "SECRET_KEY": "short",
            })

    def test_from_dict_choices_validation(self) -> None:
        # Valid choice
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a" * 20,
            "WORKERS": "4",
        })
        assert config.WORKERS == 4

        # Invalid choice
        with pytest.raises(ValidationError):
            AppConfig.from_dict({
                "APP_ENV": "production",
                "SECRET_KEY": "a" * 20,
                "WORKERS": "5",
            })

    def test_from_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(textwrap.dedent("""\
            APP_NAME=myapp
            DEBUG=true
        """))
        config = SimpleConfig.from_env_file(env_file)
        assert config.NAME == "myapp"
        assert config.DEBUG is True

    def test_optional_field_with_no_value(self) -> None:
        config = OptionalConfig.from_dict({"HOST": "localhost"})
        assert config.HOST == "localhost"
        assert config.PORT == 8080  # default
        assert config.API_KEY is None  # optional, no default

    def test_optional_field_with_value(self) -> None:
        config = OptionalConfig.from_dict({"HOST": "localhost", "API_KEY": "sk-test123"})
        assert config.API_KEY == "sk-test123"


# ── Settings representation tests ────────────────────────────────────────────

class TestEnvSettingsRepr:
    def test_repr_masks_sensitive(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "development",
            "SECRET_KEY": "super_secret_key_value_here_1234",
        })
        r = repr(config)
        assert "super_secret_key_value_here_1234" not in r
        assert "***" in r

    def test_repr_shows_non_sensitive(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "myapp", "DEBUG": "true"})
        r = repr(config)
        assert "myapp" in r
        assert "True" in r


# ── Schema generation tests ─────────────────────────────────────────────────

class TestSchema:
    def test_schema_structure(self) -> None:
        s = DatabaseConfig.schema()
        assert s["name"] == "DatabaseConfig"
        assert len(s["fields"]) == 5
        # Schema uses env_key names by default
        field_names = [f["name"] for f in s["fields"]]
        assert "DB_HOST" in field_names

    def test_schema_json(self) -> None:
        import json
        s = DatabaseConfig.schema_json()
        data = json.loads(s)
        assert data["name"] == "DatabaseConfig"

    def test_schema_field_details(self) -> None:
        s = DatabaseConfig.schema()
        port_field = next(f for f in s["fields"] if f["name"] == "DB_PORT")
        assert port_field["type"] == "int"
        assert port_field["required"] is False
        assert port_field["default"] == 5432
        assert port_field["min"] == 1
        assert port_field["max"] == 65535

    def test_schema_sensitive_field(self) -> None:
        s = DatabaseConfig.schema()
        url_field = next(f for f in s["fields"] if f["name"] == "DATABASE_URL")
        assert url_field["sensitive"] is True

    def test_schema_choices(self) -> None:
        s = AppConfig.schema()
        workers_field = next(f for f in s["fields"] if f["name"] == "WORKERS")
        assert "choices" in workers_field
        assert workers_field["choices"] == ["1", "2", "4", "8"]


# ── .env.example generation tests ───────────────────────────────────────────

class TestGenerateEnvExample:
    def test_generates_content(self) -> None:
        content = SimpleConfig.generate_env_example()
        assert "APP_NAME=" in content
        assert "DEBUG=" in content

    def test_includes_comments(self) -> None:
        content = DatabaseConfig.generate_env_example()
        assert "Database host" in content

    def test_includes_defaults(self) -> None:
        content = DatabaseConfig.generate_env_example()
        assert "5432" in content  # DB_PORT default

    def test_masks_sensitive_defaults(self) -> None:
        # Create a config with sensitive default
        class SecretConfig(EnvSettings):
            KEY = EnvField(name="API_KEY", type=str, required=True, sensitive=True, default="real-secret-value")

        content = SecretConfig.generate_env_example()
        # The comment may still contain the default; check the assignment line is masked
        for line in content.splitlines():
            if line.strip().startswith("API_KEY="):
                assert "real-secret-value" not in line

    def test_required_fields_no_default(self) -> None:
        content = SimpleConfig.generate_env_example()
        # APP_NAME is required with no default
        assert "APP_NAME=" in content


# ── Dict/access helper tests ────────────────────────────────────────────────

class TestSettingsHelpers:
    def test_as_dict(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        d = config.as_dict()
        assert d["NAME"] == "test"
        assert d["DEBUG"] is False

    def test_as_dict_masks_sensitive(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a" * 20,
        })
        d = config.as_dict(mask_sensitive=True)
        assert d["SECRET_KEY"] == "***"

    def test_as_dict_no_mask(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a" * 20,
        })
        d = config.as_dict(mask_sensitive=False)
        assert d["SECRET_KEY"] == "a" * 20

    def test_is_set(self) -> None:
        config = OptionalConfig.from_dict({"HOST": "localhost"})
        assert config.is_set("HOST") is True
        assert config.is_set("API_KEY") is False

    def test_missing_required(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        assert config.missing_required() == []

        config = OptionalConfig.from_dict({"HOST": "localhost"})
        assert config.missing_required() == []

    def test_errors(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        assert config.errors() == []
        assert config.is_valid() is True

    def test_source_of(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        assert config.source_of("NAME") == "explicit"

    def test_source_of_default(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        assert config.source_of("DEBUG") == "default"

    def test_getattr_unknown(self) -> None:
        config = SimpleConfig.from_dict({"APP_NAME": "test"})
        with pytest.raises(AttributeError):
            _ = config.NONEXISTENT


# ── Strict mode tests ──────────────────────────────────────────────────────

class TestStrictMode:
    def test_strict_unknown_vars(self) -> None:
        with pytest.raises(SettingsError, match="Unknown"):
            SimpleConfig.from_dict({"APP_NAME": "test", "UNKNOWN_VAR": "value"}, strict=True)

    def test_strict_known_vars_ok(self) -> None:
        # Should not raise when all vars are known
        config = SimpleConfig.from_dict({"APP_NAME": "test", "DEBUG": "true"}, strict=True)
        assert config.NAME == "test"


# ── Load with env file integration ──────────────────────────────────────────

class TestLoadWithEnvFile:
    def test_env_file_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=localhost\nDB_NAME=mydb\nDB_PORT=3306\n")
        config = DatabaseConfig.load(env_file=env_file)
        assert config.HOST == "localhost"
        assert config.NAME == "mydb"
        assert config.PORT == 3306

    def test_env_overrides_file(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=fromfile\nDB_NAME=mydb\n")
        monkeypatch.setenv("DB_HOST", "fromenv")
        config = DatabaseConfig.load(env_file=env_file)
        # os.environ should override .env file
        assert config.HOST == "fromenv"

    def test_explicit_overrides_all(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=fromfile\nDB_NAME=mydb\n")
        monkeypatch.setenv("DB_HOST", "fromenv")
        config = DatabaseConfig.load(
            env_file=env_file,
            env={"DB_HOST": "fromdict"},
        )
        # Explicit dict should override os.environ
        assert config.HOST == "fromdict"

    def test_nonexistent_env_file(self) -> None:
        # Should not raise, just ignore the missing file
        config = DatabaseConfig.load(
            env_file=Path("/nonexistent/.env"),
            env={"DB_HOST": "localhost", "DB_NAME": "mydb"},
        )
        assert config.HOST == "localhost"


# ── Complex nested settings tests ───────────────────────────────────────────

class TestComplexSettings:
    def test_full_app_config(self) -> None:
        config = AppConfig.from_dict({
            "APP_ENV": "production",
            "SECRET_KEY": "a_very_long_secret_key_here",
            "DEBUG": "false",
            "PORT": "443",
            "LOG_LEVEL": "warning",
            "ALLOWED_HOSTS": "app.example.com,api.example.com",
            "WORKERS": "8",
        })
        assert config.ENV == Environment.PRODUCTION
        assert config.DEBUG is False
        assert config.PORT == 443
        assert config.LOG_LEVEL == LogLevel.WARNING
        assert config.ALLOWED_HOSTS == ["app.example.com", "api.example.com"]
        assert config.WORKERS == 8

    def test_dict_type_settings(self) -> None:
        class FeatureConfig(EnvSettings):
            FLAGS = EnvField(name="FEATURE_FLAGS", type=Dict[str, str], required=True, separator=",")

        config = FeatureConfig.from_dict({"FEATURE_FLAGS": "dark_mode=enabled,beta=disabled"})
        assert config.FLAGS == {"dark_mode": "enabled", "beta": "disabled"}

    def test_tuple_type_settings(self) -> None:
        class CoordConfig(EnvSettings):
            POSITION = EnvField(name="POSITION", type=Tuple[float, float], required=True, separator=",")

        config = CoordConfig.from_dict({"POSITION": "45.5,-122.6"})
        assert config.POSITION == pytest.approx((45.5, -122.6))
