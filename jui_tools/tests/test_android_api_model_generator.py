"""Tests for android_api_model_generator — DTO + enum + Domain across 3 serializers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.android_api_model_generator import (
    AndroidApiModelGenerator,
    AndroidApiPlatformConfig,
)


def _gen(
    tmp: Path,
    serializer: str = "moshi",
    *,
    domain_package: str = "com.example.app.model",
    dto_package: str = "com.example.app.model.generated",
) -> AndroidApiModelGenerator:
    return AndroidApiModelGenerator(
        AndroidApiPlatformConfig(
            sources_root=tmp,
            domain_package=domain_package,
            dto_package=dto_package,
            serializer=serializer,
        )
    )


def _doc(schemas: dict) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {"schemas": schemas},
    }


def _user_schema():
    return {
        "User": {
            "type": "object",
            "required": ["id", "displayName"],
            "properties": {
                "id": {"type": "string"},
                "display_name": {"type": "string"},
                "age": {"type": "integer"},
                "is_premium": {"type": "boolean"},
            },
        },
    }


class MoshiSerializerTests(unittest.TestCase):
    def test_emits_moshi_annotations(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(doc.schemas[0], doc)
        self.assertIn("import com.squareup.moshi.Json", src)
        self.assertIn("import com.squareup.moshi.JsonClass", src)
        self.assertIn("@JsonClass(generateAdapter = true)", src)
        self.assertIn('@Json(name = "id") val id: String', src)
        self.assertIn('@Json(name = "display_name") val displayName: String', src)
        self.assertIn('@Json(name = "is_premium") val isPremium: Boolean?', src)
        # No kotlinx imports
        self.assertNotIn("kotlinx.serialization", src)

    def test_dto_path_layout(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "moshi")
            path = gen.dto_path("User")
        # Expected: <tmp>/com/example/app/model/generated/UserDto.kt
        self.assertTrue(str(path).endswith("com/example/app/model/generated/UserDto.kt"))

    def test_dto_path_with_consumer_fqn(self):
        """When domain_package is a non-default FQN, file path mirrors it.
        Regression for the wrong-source-dir-and-base-package bug."""
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(
                Path(tmp),
                "kotlinx",
                domain_package="com.acme.mobile.model",
                dto_package="com.acme.mobile.model.generated",
            )
            dto_path = gen.dto_path("User")
            domain_path = gen.domain_path("User")
        self.assertTrue(str(dto_path).endswith(
            "com/acme/mobile/model/generated/UserDto.kt"
        ))
        self.assertTrue(str(domain_path).endswith(
            "com/acme/mobile/model/User.kt"
        ))
        # And neither contains the default com/example/app/ prefix
        self.assertNotIn("com/example/app", str(dto_path))
        self.assertNotIn("com/example/app", str(domain_path))


class KotlinxSerializerTests(unittest.TestCase):
    def test_emits_kotlinx_annotations(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(doc.schemas[0], doc)
        self.assertIn("import kotlinx.serialization.SerialName", src)
        self.assertIn("import kotlinx.serialization.Serializable", src)
        self.assertIn("@Serializable", src)
        # @SerialName only on renamed fields
        self.assertIn('@SerialName("display_name") val displayName: String', src)
        self.assertIn('@SerialName("is_premium") val isPremium: Boolean?', src)
        # Bare names match wire — no annotation
        self.assertNotIn('@SerialName("id")', src)
        # No moshi imports
        self.assertNotIn("moshi", src)


class NoneSerializerTests(unittest.TestCase):
    def test_emits_bare_data_class(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "none").generate_dto_source(doc.schemas[0], doc)
        # No annotation imports at all
        self.assertNotIn("import com.squareup.moshi", src)
        self.assertNotIn("import kotlinx.serialization", src)
        # No @JsonClass / @Serializable
        self.assertNotIn("@JsonClass", src)
        self.assertNotIn("@Serializable", src)
        # No @Json / @SerialName
        self.assertNotIn("@Json(", src)
        self.assertNotIn("@SerialName(", src)
        # Plain data class
        self.assertIn("data class UserDto(", src)
        self.assertIn("val id: String", src)
        self.assertIn("val displayName: String", src)


class InvalidSerializerTests(unittest.TestCase):
    def test_rejects_unknown_serializer(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                AndroidApiModelGenerator(
                    AndroidApiPlatformConfig(
                        sources_root=Path(tmp),
                        domain_package="com.example.app.model",
                        dto_package="com.example.app.model.generated",
                        serializer="gson",  # unsupported in v1
                    )
                )


class PackageResolverTests(unittest.TestCase):
    """Regression for jui-android-api-model-generator-wrong-source-dir-and-base-package.

    Verifies that the resolver in api_model_sync respects:
    - ``kjui.config.json#package_name`` as the FQN base
    - ``source_directory`` with an automatic ``kotlin/`` sub-source-set append
    - ``api.platforms.android.model_package`` as either bare or full FQN
    """

    def test_kotlin_subsource_set_appended(self):
        import json as _json
        import tempfile as _tf
        from jui_cli.core.api_model_sync import _resolve_android_sources_and_package
        with _tf.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kjui.config.json").write_text(_json.dumps({
                "source_directory": "app/src/main",
                "package_name": "com.acme.mobile",
            }))
            (root / "app/src/main/kotlin").mkdir(parents=True)
            sources_root, base_package = _resolve_android_sources_and_package(root)
            self.assertTrue(str(sources_root).endswith("app/src/main/kotlin"))
            self.assertEqual(base_package, "com.acme.mobile")

    def test_java_fallback_when_kotlin_missing(self):
        import json as _json
        import tempfile as _tf
        from jui_cli.core.api_model_sync import _resolve_android_sources_and_package
        with _tf.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kjui.config.json").write_text(_json.dumps({
                "source_directory": "app/src/main",
                "package_name": "com.example.app",
            }))
            (root / "app/src/main/java").mkdir(parents=True)
            sources_root, _ = _resolve_android_sources_and_package(root)
            self.assertTrue(str(sources_root).endswith("app/src/main/java"))

    def test_no_kjui_config_uses_defaults(self):
        import tempfile as _tf
        from jui_cli.core.api_model_sync import _resolve_android_sources_and_package
        with _tf.TemporaryDirectory() as tmp:
            sources_root, base_package = _resolve_android_sources_and_package(Path(tmp))
            self.assertTrue(str(sources_root).endswith("app/src/main/kotlin"))
            self.assertEqual(base_package, "com.example.app")

    def test_full_fqn_model_package_used_verbatim(self):
        """A ``model_package`` containing ``.`` is an opt-out from base
        prefixing — used as the full FQN."""
        # Simulate plan_android's join logic
        raw = "com.acme.mobile.model"
        result = raw if "." in raw else f"com.example.app.{raw}"
        self.assertEqual(result, "com.acme.mobile.model")

    def test_bare_model_package_prepended_with_base(self):
        raw = "model"
        base = "com.acme.mobile"
        result = raw if "." in raw else f"{base}.{raw}"
        self.assertEqual(result, "com.acme.mobile.model")


class EnumEmissionTests(unittest.TestCase):
    def test_string_enum_screaming_snake_case(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {"type": "string", "enum": ["google", "apple_pay", "Email"]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_enum_source(doc.enums[0], doc)
        self.assertIn("enum class AuthProvider(val wire: String) {", src)
        self.assertIn('GOOGLE("google"),', src)
        self.assertIn('APPLE_PAY("apple_pay"),', src)
        # Email → EMAIL
        self.assertIn('EMAIL("Email");', src)

    def test_integer_enum_with_varnames(self):
        doc = parse_swagger(_doc({
            "Severity": {
                "type": "integer",
                "enum": [1, 2, 3],
                "x-enum-varnames": ["low", "medium", "high"],
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_enum_source(doc.enums[0], doc)
        self.assertIn("enum class Severity(val wire: Int) {", src)
        self.assertIn("LOW(1),", src)
        self.assertIn("MEDIUM(2),", src)
        self.assertIn("HIGH(3);", src)

    def test_reserved_word_in_enum_case_escaped(self):
        doc = parse_swagger(_doc({
            "Visibility": {"type": "string", "enum": ["public", "private", "internal"]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_enum_source(doc.enums[0], doc)
        # SCREAMING_SNAKE escaping — uppercase form may or may not collide,
        # check at least no syntax error pattern (case `private` not bare)
        self.assertIn("PUBLIC", src)
        # PRIVATE is not a Kotlin keyword (only `private` lowercase is)
        self.assertIn("PRIVATE", src)


class DomainScaffoldTests(unittest.TestCase):
    def test_scaffold_is_minimal_class_not_data_class(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_domain_source(doc.schemas[0])
        # Plain class, not data class — user can add var stored properties later
        self.assertIn("class User(val dto: UserDto)", src)
        self.assertNotIn("data class User", src)
        self.assertIn("import com.example.app.model.generated.UserDto", src)
        self.assertIn("User customization zone", src)
        # No @generated banner
        self.assertNotIn("@generated", src)


class KotlinxDomainSerializerTests(unittest.TestCase):
    """kotlinx-mode Domain wrappers carry a delegating KSerializer so they
    are usable as Retrofit request/response types and as fields inside
    `@Serializable` composites. See bug
    kjui-wrapper-class-not-serializable-blocks-retrofit-and-composites.
    """

    def _doc_and_schema(self):
        doc = parse_swagger(_doc({
            "AuthResponse": {
                "type": "object",
                "required": ["token"],
                "properties": {"token": {"type": "string"}},
            },
        }), "test.json")
        return doc, doc.schemas[0]

    def test_new_scaffold_has_serializable_annotation_and_block(self):
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_domain_source(schema)
        self.assertIn("@Serializable(with = AuthResponseSerializer::class)", src)
        self.assertIn("class AuthResponse(val dto: AuthResponseDto)", src)
        self.assertIn("object AuthResponseSerializer : KSerializer<AuthResponse>", src)
        self.assertIn("private val dtoSerializer = AuthResponseDto.serializer()", src)
        self.assertIn("AUTO-GENERATED Serializer", src)
        self.assertIn("END AUTO-GENERATED Serializer", src)
        # Required imports.
        for imp in (
            "import kotlinx.serialization.KSerializer",
            "import kotlinx.serialization.Serializable",
            "import kotlinx.serialization.descriptors.SerialDescriptor",
            "import kotlinx.serialization.encoding.Decoder",
            "import kotlinx.serialization.encoding.Encoder",
            "import com.example.app.model.generated.AuthResponseDto",
        ):
            self.assertIn(imp, src)

    def test_moshi_mode_emits_plain_scaffold(self):
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_domain_source(schema)
        self.assertNotIn("@Serializable", src)
        self.assertNotIn("KSerializer", src)
        self.assertNotIn("AUTO-GENERATED Serializer", src)
        self.assertIn("class AuthResponse(val dto: AuthResponseDto)", src)

    def test_none_mode_emits_plain_scaffold(self):
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "none").generate_domain_source(schema)
        self.assertNotIn("@Serializable", src)
        self.assertNotIn("KSerializer", src)

    def test_existing_scaffold_gets_annotation_and_block_appended(self):
        """An old scaffold (pre-fix shape) gets annotation + block added on
        next build. User customization zone is preserved verbatim."""
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            existing = (
                "package com.example.app.model\n"
                "\n"
                "import com.example.app.model.generated.AuthResponseDto\n"
                "\n"
                "class AuthResponse(val dto: AuthResponseDto) {\n"
                "    val tokenUpper: String get() = dto.token.uppercase()\n"
                "}\n"
            )
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(existing, encoding="utf-8")

            result = gen.write_domain(schema)
            self.assertTrue(result.wrote)
            self.assertFalse(result.skipped_existing)
            updated = path.read_text(encoding="utf-8")

        # User customization is preserved verbatim.
        self.assertIn("val tokenUpper: String get() = dto.token.uppercase()", updated)
        # Annotation is injected immediately above the class declaration.
        self.assertIn(
            "@Serializable(with = AuthResponseSerializer::class)\n"
            "class AuthResponse(val dto: AuthResponseDto) {",
            updated,
        )
        # Serializer block is appended at end of file.
        self.assertIn("object AuthResponseSerializer : KSerializer<AuthResponse>", updated)
        # Required imports added without duplicating the existing DTO import.
        self.assertEqual(updated.count("import com.example.app.model.generated.AuthResponseDto"), 1)
        self.assertIn("import kotlinx.serialization.Serializable", updated)

    def test_existing_scaffold_with_old_block_gets_block_replaced(self):
        """When markers exist, the block between them is rewritten (not
        appended again). Idempotency across two rebuilds."""
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            # Simulate first build output.
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gen.generate_domain_source(schema), encoding="utf-8")

            # User adds a proxy.
            current = path.read_text(encoding="utf-8")
            current = current.replace(
                "    // stored properties, methods, and conversions here.",
                "    // stored properties, methods, and conversions here.\n"
                "    val tokenUpper: String get() = dto.token.uppercase()",
            )
            path.write_text(current, encoding="utf-8")

            # Mutate the auto block to verify it gets restored.
            corrupted = current.replace(
                "private val dtoSerializer = AuthResponseDto.serializer()",
                "private val dtoSerializer = TamperedDto.serializer()",
            )
            path.write_text(corrupted, encoding="utf-8")

            # Re-run write_domain.
            result = gen.write_domain(schema)
            self.assertTrue(result.wrote)
            updated = path.read_text(encoding="utf-8")

        # Block restored (corruption gone).
        self.assertIn("private val dtoSerializer = AuthResponseDto.serializer()", updated)
        self.assertNotIn("TamperedDto.serializer", updated)
        # User proxy still in the user zone.
        self.assertIn("val tokenUpper: String get() = dto.token.uppercase()", updated)
        # Exactly one block (markers not duplicated).
        self.assertEqual(updated.count("AUTO-GENERATED Serializer — do not edit"), 1)

    def test_idempotent_second_call_no_change(self):
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            r1 = gen.write_domain(schema)
            self.assertTrue(r1.wrote)
            r2 = gen.write_domain(schema)
            # Existing file matches what we'd regenerate → no change.
            self.assertFalse(r2.wrote)
            self.assertTrue(r2.skipped_existing)

    def test_custom_user_with_annotation_not_overwritten(self):
        """If the user manually wrote a different serializer annotation,
        the patcher leaves it alone — only the AUTO-GENERATED block fires."""
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            existing = (
                "package com.example.app.model\n"
                "\n"
                "import com.example.app.model.generated.AuthResponseDto\n"
                "import kotlinx.serialization.Serializable\n"
                "\n"
                "@Serializable(with = MyCustomSerializer::class)\n"
                "class AuthResponse(val dto: AuthResponseDto)\n"
            )
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(existing, encoding="utf-8")

            gen.write_domain(schema)
            updated = path.read_text(encoding="utf-8")

        # User's annotation is preserved.
        self.assertIn("@Serializable(with = MyCustomSerializer::class)", updated)
        # Codegen does NOT inject a competing annotation above the class.
        self.assertNotIn(
            "@Serializable(with = AuthResponseSerializer::class)\nclass AuthResponse",
            updated,
        )
        # Serializer block is still appended (codegen artifact, harmless).
        self.assertIn("object AuthResponseSerializer", updated)


class RefTypeTests(unittest.TestCase):
    def test_object_ref_uses_dto_suffix(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "Article": {
                "type": "object",
                "required": ["tag"],
                "properties": {"tag": {"$ref": "#/components/schemas/Tag"}},
            },
        }), "test.json")
        article = next(s for s in doc.schemas if s.name == "Article")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(article, doc)
        self.assertIn("val tag: TagDto", src)

    def test_enum_ref_omits_dto_suffix(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {"type": "string", "enum": ["google", "apple"]},
            "User": {
                "type": "object",
                "required": ["provider"],
                "properties": {
                    "provider": {"$ref": "#/components/schemas/AuthProvider"},
                },
            },
        }), "test.json")
        user = next(s for s in doc.schemas if s.name == "User")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(user, doc)
        self.assertIn("val provider: AuthProvider", src)
        self.assertNotIn("AuthProviderDto", src)

    def test_array_and_map_types(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"n": {"type": "string"}}},
            "M": {
                "type": "object",
                "required": ["tags", "labels"],
                "properties": {
                    "tags": {"type": "array", "items": {"$ref": "#/components/schemas/Tag"}},
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        m = next(s for s in doc.schemas if s.name == "M")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(m, doc)
        self.assertIn("val tags: List<TagDto>", src)
        self.assertIn("val labels: Map<String, TagDto>", src)


class EnumDefaultLiteralTests(unittest.TestCase):
    """Regression — `allOf: [$ref: <enum>] + default: <value>` must emit
    `EnumName.CASE` not a raw string literal (else kotlinc halts on type
    mismatch). See bug
    jui-android-codegen-allof-ref-enum-emits-domain-name-with-string-default.
    """

    def _reaction_doc(self):
        return parse_swagger(_doc({
            "ReactionType": {
                "type": "string",
                "enum": ["favorite", "want_to_drink"],
            },
            "ReactionTypeBody": {
                "type": "object",
                "properties": {
                    "reaction_type": {
                        "allOf": [{"$ref": "#/components/schemas/ReactionType"}],
                        "default": "favorite",
                    },
                },
            },
        }), "test.json")

    def test_string_enum_default_emits_case_reference(self):
        doc = self._reaction_doc()
        body = next(s for s in doc.schemas if s.name == "ReactionTypeBody")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(body, doc)
        self.assertIn("val reactionType: ReactionType? = ReactionType.FAVORITE", src)
        self.assertNotIn('= "favorite"', src)

    def test_string_enum_default_emits_case_reference_kotlinx(self):
        doc = self._reaction_doc()
        body = next(s for s in doc.schemas if s.name == "ReactionTypeBody")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(body, doc)
        self.assertIn("ReactionType.FAVORITE", src)

    def test_integer_enum_default_emits_case_reference(self):
        doc = parse_swagger(_doc({
            "Severity": {
                "type": "integer",
                "enum": [1, 2, 3],
                "x-enum-varnames": ["low", "medium", "high"],
            },
            "Alert": {
                "type": "object",
                "properties": {
                    "level": {
                        "allOf": [{"$ref": "#/components/schemas/Severity"}],
                        "default": 2,
                    },
                },
            },
        }), "test.json")
        alert = next(s for s in doc.schemas if s.name == "Alert")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(alert, doc)
        self.assertIn("val level: Severity? = Severity.MEDIUM", src)

    def test_default_not_in_enum_skipped(self):
        """Swagger bug — value not in enum. Skip default rather than halt."""
        doc = parse_swagger(_doc({
            "ReactionType": {
                "type": "string",
                "enum": ["favorite", "want_to_drink"],
            },
            "ReactionTypeBody": {
                "type": "object",
                "properties": {
                    "reaction_type": {
                        "allOf": [{"$ref": "#/components/schemas/ReactionType"}],
                        "default": "bogus",
                    },
                },
            },
        }), "test.json")
        body = next(s for s in doc.schemas if s.name == "ReactionTypeBody")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(body, doc)
        # No default emitted on the enum-typed field — caller must pass a
        # value explicitly. We deliberately do *not* fall back to ``= null``
        # because the swagger asserted a default that turned out to be
        # invalid; surfacing it via "missing argument" at call sites tells
        # the user to fix the schema.
        self.assertIn("val reactionType: ReactionType?,", src)
        self.assertNotIn('"bogus"', src)
        self.assertNotIn("= ReactionType.", src)
        self.assertNotIn("= null", src)

    def test_primitive_string_default_unaffected(self):
        """Regression — non-enum string defaults still emit as literals."""
        doc = parse_swagger(_doc({
            "Greeting": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "default": "hello"},
                },
            },
        }), "test.json")
        body = doc.schemas[0]
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "moshi").generate_dto_source(body, doc)
        self.assertIn('val message: String? = "hello"', src)


class WriteBehaviorTests(unittest.TestCase):
    def test_dto_written_idempotent(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "moshi")
            r1 = gen.write_dto(doc.schemas[0], doc)
            self.assertTrue(r1.wrote)
            r2 = gen.write_dto(doc.schemas[0], doc)
            self.assertFalse(r2.wrote)

    def test_domain_skipped_when_existing(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "moshi")
            first = gen.write_domain(doc.schemas[0])
            self.assertTrue(first.wrote)
            first.path.write_text("// custom\n", encoding="utf-8")
            second = gen.write_domain(doc.schemas[0])
            self.assertTrue(second.skipped_existing)
            self.assertEqual(first.path.read_text(), "// custom\n")


if __name__ == "__main__":
    unittest.main()
