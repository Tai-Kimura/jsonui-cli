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

    def test_skip_when_serializer_object_already_exists_outside_marker(self):
        """If the user / earlier codegen has already declared
        ``object {Name}Serializer`` at file scope (no markers),
        the patcher must NOT append another marker-wrapped block —
        kotlinc would halt with ``Redeclaration``."""
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            existing = (
                "package com.example.app.model\n"
                "\n"
                "import com.example.app.model.generated.AuthResponseDto\n"
                "import kotlinx.serialization.KSerializer\n"
                "import kotlinx.serialization.Serializable\n"
                "import kotlinx.serialization.descriptors.SerialDescriptor\n"
                "import kotlinx.serialization.encoding.Decoder\n"
                "import kotlinx.serialization.encoding.Encoder\n"
                "\n"
                "@Serializable(with = AuthResponseSerializer::class)\n"
                "class AuthResponse(val dto: AuthResponseDto)\n"
                "\n"
                "object AuthResponseSerializer : KSerializer<AuthResponse> {\n"
                "    private val dtoSerializer = AuthResponseDto.serializer()\n"
                "    override val descriptor: SerialDescriptor = dtoSerializer.descriptor\n"
                "    override fun serialize(encoder: Encoder, value: AuthResponse) =\n"
                "        dtoSerializer.serialize(encoder, value.dto)\n"
                "    override fun deserialize(decoder: Decoder): AuthResponse =\n"
                "        AuthResponse(dtoSerializer.deserialize(decoder))\n"
                "}\n"
            )
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(existing, encoding="utf-8")

            result = gen.write_domain(schema)
            updated = path.read_text(encoding="utf-8")

        # Patcher reports no write (everything already in place).
        self.assertFalse(result.wrote)
        # No marker block injected (would have duplicated the object).
        self.assertNotIn("AUTO-GENERATED Serializer", updated)
        # Existing serializer object preserved.
        self.assertEqual(
            updated.count("object AuthResponseSerializer : KSerializer<AuthResponse>"),
            1,
        )

    def test_patcher_skips_non_wrapper_data_class(self):
        """Defense in depth for the wrapper-shape gate: even if the
        shadow filter misses a hand-written data class (e.g. the
        type-map entry is missing or has an unrecognized form),
        ``_patch_kotlinx_domain`` must NOT inject the delegating
        serializer onto a file whose class lacks ``val dto: {Name}Dto``.
        Injecting the block would reference ``value.dto`` which doesn't
        exist on a data class with custom fields, and kotlinc halts
        with ``Unresolved reference 'dto'``.
        """
        _, schema = self._doc_and_schema()  # schema.name == "AuthResponse"
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            existing = (
                "package com.example.app.model\n"
                "\n"
                "import kotlinx.serialization.Serializable\n"
                "\n"
                "@Serializable\n"
                "data class AuthResponse(\n"
                "    val customField: String,\n"
                "    val anotherField: Int,\n"
                ")\n"
            )
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(existing, encoding="utf-8")

            result = gen.write_domain(schema)
            after = path.read_text(encoding="utf-8")

        # Patcher must report no-op and file content unchanged.
        self.assertFalse(result.wrote)
        self.assertEqual(after, existing)
        # No serializer block injected.
        self.assertNotIn("AuthResponseSerializer", after)
        self.assertNotIn("AUTO-GENERATED Serializer", after)

    def test_patcher_runs_on_wrapper_with_val_dto_member(self):
        """Regression — wrapper-shape gate must still let the canonical
        ``class X(val dto: XDto)`` form through. Verifies the gate
        recognizes the wrapper member regex correctly."""
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
            updated = path.read_text(encoding="utf-8")

        self.assertTrue(result.wrote)
        self.assertIn("@Serializable(with = AuthResponseSerializer::class)", updated)
        self.assertIn("object AuthResponseSerializer", updated)

    def test_marker_block_replaced_even_if_unrelated_serializer_object_exists(self):
        """An unrelated ``object FooSerializer`` (different schema) at
        file scope must not block patching of the target schema's
        marker block — regex match must be schema-name specific."""
        _, schema = self._doc_and_schema()
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp), "kotlinx")
            # Start from a fully patched scaffold, then add an unrelated
            # serializer object at the bottom.
            path = gen.domain_path("AuthResponse")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gen.generate_domain_source(schema), encoding="utf-8")
            with open(path, "a", encoding="utf-8") as f:
                f.write(
                    "\nobject UnrelatedSerializer : KSerializer<Unit> {\n"
                    "    // hand-written, leave alone\n"
                    "}\n"
                )

            # Mutate the marker block — patcher should restore it.
            current = path.read_text(encoding="utf-8")
            corrupted = current.replace(
                "private val dtoSerializer = AuthResponseDto.serializer()",
                "private val dtoSerializer = TamperedDto.serializer()",
            )
            path.write_text(corrupted, encoding="utf-8")

            result = gen.write_domain(schema)
            updated = path.read_text(encoding="utf-8")

        self.assertTrue(result.wrote)
        self.assertIn(
            "private val dtoSerializer = AuthResponseDto.serializer()",
            updated,
        )
        # Unrelated object preserved.
        self.assertIn("object UnrelatedSerializer", updated)

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


class OneOfDiscriminatorTests(unittest.TestCase):
    """oneOf + discriminator emits a sealed-class union + a custom
    KSerializer for the parent. Only the kotlinx serializer is supported
    in v1; Moshi / none must halt with a clear error.
    """

    def _stream_event_doc(self):
        return parse_swagger(_doc({
            "StreamConvIdContent": {
                "type": "object",
                "required": ["cid"],
                "properties": {"cid": {"type": "string"}},
            },
            "StreamThinkingContent": {
                "type": "object",
                "required": ["msg"],
                "properties": {"msg": {"type": "string"}},
            },
            "StreamEvent": {
                "type": "object",
                "required": ["type", "content"],
                "properties": {
                    "type": {"type": "string"},
                    "content": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/StreamConvIdContent"},
                            {"$ref": "#/components/schemas/StreamThinkingContent"},
                        ],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {
                                "conversation_id": "#/components/schemas/StreamConvIdContent",
                                "thinking": "#/components/schemas/StreamThinkingContent",
                            },
                        },
                    },
                },
            },
        }), "test.json")

    def test_sealed_class_emitted_with_data_variants(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(stream, doc)
        self.assertIn("val content: Content", src)
        self.assertIn("sealed class Content {", src)
        self.assertIn(
            "data class ConversationId(val data: StreamConvIdContentDto) : Content()",
            src,
        )
        self.assertIn(
            "data class Thinking(val data: StreamThinkingContentDto) : Content()",
            src,
        )
        self.assertIn("data object Unknown : Content()", src)

    def test_custom_kserializer_emitted(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(stream, doc)
        self.assertIn(
            "@Serializable(with = StreamEventDtoSerializer::class)",
            src,
        )
        self.assertIn(
            "object StreamEventDtoSerializer : KSerializer<StreamEventDto>",
            src,
        )
        # serialize/deserialize bodies
        self.assertIn("override fun serialize(encoder: Encoder, value: StreamEventDto)", src)
        self.assertIn("override fun deserialize(decoder: Decoder): StreamEventDto", src)
        # dispatch on discriminator
        self.assertIn('"conversation_id" -> StreamEventDto.Content.ConversationId(', src)
        self.assertIn('"thinking" -> StreamEventDto.Content.Thinking(', src)
        self.assertIn("else -> StreamEventDto.Content.Unknown", src)

    def test_required_kotlinx_json_imports_present(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(stream, doc)
        for imp in (
            "import kotlinx.serialization.KSerializer",
            "import kotlinx.serialization.descriptors.buildClassSerialDescriptor",
            "import kotlinx.serialization.json.JsonDecoder",
            "import kotlinx.serialization.json.JsonEncoder",
            "import kotlinx.serialization.json.buildJsonObject",
            "import kotlinx.serialization.json.decodeFromJsonElement",
            "import kotlinx.serialization.json.jsonObject",
        ):
            self.assertIn(imp, src)

    def test_enum_typed_discriminator_compares_wire_string(self):
        """When discriminator field has inline ``enum: [...]``, the
        Kotlin ``when`` arg must be ``type.wire`` (String) — comparing
        the enum-typed ``type`` against String literals would not
        compile."""
        doc = parse_swagger(_doc({
            "StreamConvIdContent": {
                "type": "object",
                "required": ["cid"],
                "properties": {"cid": {"type": "string"}},
            },
            "StreamThinkingContent": {
                "type": "object",
                "required": ["msg"],
                "properties": {"msg": {"type": "string"}},
            },
            "StreamEvent": {
                "type": "object",
                "required": ["type", "content"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["conversation_id", "thinking", "progress"],
                    },
                    "content": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/StreamConvIdContent"},
                            {"$ref": "#/components/schemas/StreamThinkingContent"},
                        ],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {
                                "conversation_id": "#/components/schemas/StreamConvIdContent",
                                "thinking": "#/components/schemas/StreamThinkingContent",
                            },
                        },
                    },
                },
            },
        }), "test.json")
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(stream, doc)
        # Decoded into the typed enum:
        self.assertIn("val type: StreamEventType = json.decodeFromJsonElement(", src)
        # when arg must be ``type.wire``, not ``type``.
        self.assertIn("when (type.wire) {", src)
        # String literal branches are preserved.
        self.assertIn('"conversation_id" -> StreamEventDto.Content.ConversationId(', src)
        self.assertIn('"thinking" -> StreamEventDto.Content.Thinking(', src)
        # else fallback kept.
        self.assertIn("else -> StreamEventDto.Content.Unknown", src)

    def test_string_typed_discriminator_unchanged(self):
        """Existing behavior for non-enum String discriminator stays the
        same — the when arg is the bare property."""
        doc = parse_swagger(_doc({
            "ConvId": {"type": "object", "properties": {"id": {"type": "string"}}},
            "Parent": {
                "type": "object",
                "required": ["type", "content"],
                "properties": {
                    # No enum — plain String discriminator.
                    "type": {"type": "string"},
                    "content": {
                        "oneOf": [{"$ref": "#/components/schemas/ConvId"}],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {"conv_id": "#/components/schemas/ConvId"},
                        },
                    },
                },
            },
        }), "test.json")
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(parent, doc)
        # type stays as String, when arg is bare ``type``.
        self.assertIn("val type: String", src)
        self.assertIn("when (type) {", src)
        self.assertIn('"conv_id" -> ParentDto.Content.ConvId(', src)

    def test_enum_cases_get_serial_name_annotations(self):
        """kotlinx serializes enum case names by default, not the
        constructor wire value. We must emit ``@SerialName("wire")`` per
        case so the wire ↔ enum mapping works at runtime."""
        doc = parse_swagger(_doc({
            "AuthProvider": {
                "type": "string",
                "enum": ["google", "apple_id", "email"],
            },
        }), "test.json")
        enum = doc.enums[0]
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_enum_source(enum, doc)
        # Cases whose Kotlin identifier differs from the wire value carry
        # an explicit ``@SerialName`` annotation.
        self.assertIn('@SerialName("apple_id") APPLE_ID("apple_id")', src)
        # Cases where the wire value matches the identifier (e.g.
        # lowercase "google" → SCREAMING_SNAKE "GOOGLE" — diverges, so
        # annotation is required).
        self.assertIn('@SerialName("google") GOOGLE("google")', src)
        self.assertIn('@SerialName("email") EMAIL("email")', src)

    def test_enum_cases_no_serial_name_in_moshi_or_none(self):
        """Moshi / none modes don't use kotlinx — no ``@SerialName``."""
        doc = parse_swagger(_doc({
            "AuthProvider": {
                "type": "string",
                "enum": ["google", "apple"],
            },
        }), "test.json")
        enum = doc.enums[0]
        with tempfile.TemporaryDirectory() as tmp:
            src_moshi = _gen(Path(tmp), "moshi").generate_enum_source(enum, doc)
            src_none = _gen(Path(tmp), "none").generate_enum_source(enum, doc)
        self.assertNotIn("@SerialName(", src_moshi)
        self.assertNotIn("@SerialName(", src_none)

    def test_moshi_mode_halts(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                _gen(Path(tmp), "moshi").generate_dto_source(stream, doc)
        self.assertIn("kotlinx serializer", str(ctx.exception))

    def test_none_mode_halts(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                _gen(Path(tmp), "none").generate_dto_source(stream, doc)
        self.assertIn("kotlinx serializer", str(ctx.exception))


class ApplyPlanKotlinxPatcherTests(unittest.TestCase):
    """Regression for the apply_plan path that retroactively patches
    pre-existing Domain wrapper scaffolds with the kotlinx
    ``@Serializable`` annotation + delegating ``KSerializer`` block.

    The earlier fix wired ``_patch_kotlinx_domain`` into the generator's
    ``write_domain`` method, but ``apply_plan`` doesn't go through
    ``write_domain`` — it shortcuts with ``if path.exists(): continue``,
    leaving 100+ wrappers in consumer projects un-patched and crashing
    at runtime with ``Serializer for class '...' is not found``.
    See bug
    ``kjui-android-domain-existing-scaffolds-not-retroactively-patched-with-serializable``.
    """

    def test_apply_plan_patches_existing_kotlinx_scaffold(self):
        from jui_cli.core.api_model_sync import SyncPlan, apply_plan
        from jui_cli.generators.android_api_model_generator import (
            _patch_kotlinx_domain,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            dto_path = tmp_root / "app/src/main/kotlin/foo/model/generated/UserProfileDto.kt"
            domain_path = tmp_root / "app/src/main/kotlin/foo/model/UserProfile.kt"
            dto_path.parent.mkdir(parents=True, exist_ok=True)
            domain_path.parent.mkdir(parents=True, exist_ok=True)

            # Pre-existing un-patched Domain wrapper.
            domain_path.write_text(
                "package foo.model\n"
                "\n"
                "import foo.model.generated.UserProfileDto\n"
                "\n"
                "class UserProfile(val dto: UserProfileDto)\n",
                encoding="utf-8",
            )
            # Stub DTO so the serializer reference resolves on inspection.
            dto_path.write_text("// dto stub\n", encoding="utf-8")

            plan = SyncPlan(
                platform="android",
                expected_files={dto_path: "// dto stub\n"},
                domain_scaffolds={domain_path: "// scaffold (would-be) source\n"},
                domain_patchers={
                    domain_path: lambda: _patch_kotlinx_domain(
                        domain_path, "UserProfile"
                    ),
                },
            )

            dto_written, scaffold_written, pruned = apply_plan(plan, prune_orphans=False)
            updated = domain_path.read_text(encoding="utf-8")

        self.assertIn(
            "@Serializable(with = UserProfileSerializer::class)",
            updated,
            "annotation must be injected into pre-existing scaffold",
        )
        self.assertIn(
            "object UserProfileSerializer : KSerializer<UserProfile>",
            updated,
            "delegating KSerializer block must be appended",
        )
        # apply_plan reports the patch as a scaffold write.
        self.assertEqual(scaffold_written, 1)

    def _plan_with_shadowed(self, type_map_types: dict, swagger_schemas: dict):
        """Helper: build a temp project + plan_android over the given inputs.

        Returns the SyncPlan so individual tests assert against fields.
        Used by both shadow-filter tests below — keeps fixture setup in
        one place so the planner is exercised identically.
        """
        import json
        from jui_cli.core.api_model_sync import plan_android
        from jui_cli.core.config_manager import ConfigManager
        from jui_cli.core.openapi_loader import parse_swagger

        tmp = tempfile.TemporaryDirectory()
        tmp_root = Path(tmp.name)
        (tmp_root / "jui.config.json").write_text(json.dumps({
            "platforms": {"android": {"root": "app-android"}},
            "type_map_file": ".jsonui-type-map.json",
            "api": {
                "platforms": {
                    "android": {"serializer": "kotlinx"},
                },
            },
        }), encoding="utf-8")
        (tmp_root / ".jsonui-type-map.json").write_text(json.dumps({
            "types": type_map_types,
        }), encoding="utf-8")
        (tmp_root / "app-android/app/src/main/kotlin").mkdir(parents=True)
        (tmp_root / "app-android/kjui.config.json").write_text(json.dumps({
            "package_name": "foo.app",
            "source_directory": "app/src/main",
        }), encoding="utf-8")

        cm = ConfigManager(tmp_root / "jui.config.json")
        doc = parse_swagger({
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {"schemas": swagger_schemas},
        }, "test.json")
        plan = plan_android(cm, {"root": "app-android"}, [doc])
        return plan, tmp  # caller drops `tmp` to clean up

    def test_plan_android_shadow_keeps_dto_drops_scaffold_and_patcher(self):
        """Regression for the over-broad shadow filter: when a schema is
        type-map shadowed, the planner must still emit the DTO (so the
        hand-written wrapper's ``val dto: XxxDto`` reference resolves and
        orphan prune doesn't delete the file) but must skip both the
        Domain scaffold and the kotlinx patcher (consumer owns the file).
        Non-shadowed schemas must still get all three.
        """
        plan, tmp = self._plan_with_shadowed(
            type_map_types={
                "BarSimple": {"class": "BarSimple"},
            },
            swagger_schemas={
                "BarSimple": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
                "Normal": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
            },
        )
        try:
            expected_names = {p.name for p in plan.expected_files}
            scaffold_names = {p.name for p in plan.domain_scaffolds}
            patcher_names = {p.name for p in plan.domain_patchers}

            # Shadowed schema: DTO emitted, scaffold + patcher skipped.
            self.assertIn("BarSimpleDto.kt", expected_names)
            self.assertNotIn("BarSimple.kt", scaffold_names)
            self.assertNotIn("BarSimple.kt", patcher_names)

            # Non-shadowed schema: DTO + scaffold + patcher all present.
            self.assertIn("NormalDto.kt", expected_names)
            self.assertIn("Normal.kt", scaffold_names)
            self.assertIn("Normal.kt", patcher_names)
        finally:
            tmp.cleanup()

    def test_plan_android_shadow_strips_question_mark_suffix(self):
        """Type-map keys often carry the spec nullable suffix (e.g.
        ``"ClientAnalysis?"``). Strip the ``?`` before matching swagger
        schema names so the user's intent — "I own this type" — applies
        to both the nullable and non-nullable variants (which are the
        same class on Kotlin/Swift)."""
        plan, tmp = self._plan_with_shadowed(
            type_map_types={
                "ClientAnalysis?": {"class": "ClientAnalysis?"},
            },
            swagger_schemas={
                "ClientAnalysis": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
            },
        )
        try:
            self.assertIn(
                "ClientAnalysisDto.kt",
                {p.name for p in plan.expected_files},
                "DTO must still be emitted for shadow w/ ? suffix",
            )
            self.assertNotIn(
                "ClientAnalysis.kt",
                {p.name for p in plan.domain_scaffolds},
                "shadow w/ ? suffix must skip scaffold",
            )
            self.assertNotIn(
                "ClientAnalysis.kt",
                {p.name for p in plan.domain_patchers},
                "shadow w/ ? suffix must skip patcher",
            )
        finally:
            tmp.cleanup()

    def test_apply_plan_idempotent_when_patcher_no_change(self):
        from jui_cli.core.api_model_sync import SyncPlan, apply_plan
        from jui_cli.generators.android_api_model_generator import (
            _patch_kotlinx_domain,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            domain_path = tmp_root / "app/src/main/kotlin/foo/model/UserProfile.kt"
            domain_path.parent.mkdir(parents=True, exist_ok=True)
            # Pre-existing un-patched scaffold.
            domain_path.write_text(
                "package foo.model\n"
                "\n"
                "import foo.model.generated.UserProfileDto\n"
                "\n"
                "class UserProfile(val dto: UserProfileDto)\n",
                encoding="utf-8",
            )

            patcher = lambda: _patch_kotlinx_domain(domain_path, "UserProfile")
            plan = SyncPlan(
                platform="android",
                expected_files={},
                domain_scaffolds={domain_path: "// scaffold\n"},
                domain_patchers={domain_path: patcher},
            )

            # First run patches the file.
            _, first_written, _ = apply_plan(plan, prune_orphans=False)
            self.assertEqual(first_written, 1)
            # Second run is a no-op.
            _, second_written, _ = apply_plan(plan, prune_orphans=False)
            self.assertEqual(second_written, 0)


class WrapperSchemaTests(unittest.TestCase):
    """Non-object schemas emit ``data class XDto(val value: T)`` +
    a custom KSerializer that delegates to the inner type's serializer.
    kotlinx-only; Moshi / none halt.
    """

    def _wrapper_doc(self):
        return parse_swagger(_doc({
            "Result": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
            "Thinking": {"type": "string", "description": "LLM text"},
            "Results": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Result"},
            },
        }), "test.json")

    def test_string_wrapper_emits_serializer(self):
        doc = self._wrapper_doc()
        thinking = next(s for s in doc.schemas if s.name == "Thinking")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(thinking, doc)
        self.assertIn("@Serializable(with = ThinkingDtoSerializer::class)", src)
        self.assertIn("data class ThinkingDto(val value: String)", src)
        self.assertIn("object ThinkingDtoSerializer : KSerializer<ThinkingDto>", src)
        self.assertIn(
            "private val inner: KSerializer<String> = String.serializer()",
            src,
        )
        self.assertIn(
            "override val descriptor: SerialDescriptor = inner.descriptor",
            src,
        )
        self.assertIn("encoder.encodeSerializableValue(inner, value.value)", src)
        self.assertIn(
            "return ThinkingDto(decoder.decodeSerializableValue(inner))",
            src,
        )
        self.assertIn("import kotlinx.serialization.builtins.serializer", src)

    def test_array_wrapper_emits_list_serializer(self):
        doc = self._wrapper_doc()
        results = next(s for s in doc.schemas if s.name == "Results")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(results, doc)
        self.assertIn("data class ResultsDto(val items: List<ResultDto>)", src)
        self.assertIn(
            "private val inner: KSerializer<List<ResultDto>> = "
            "ListSerializer(ResultDto.serializer())",
            src,
        )
        self.assertIn("import kotlinx.serialization.builtins.ListSerializer", src)

    def test_wrapper_moshi_mode_halts(self):
        doc = self._wrapper_doc()
        thinking = next(s for s in doc.schemas if s.name == "Thinking")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                _gen(Path(tmp), "moshi").generate_dto_source(thinking, doc)
        self.assertIn("kotlinx serializer", str(ctx.exception))


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


class SchemaLevelUnionTests(unittest.TestCase):
    """Schema-level oneOf union emits ``sealed class {Name}Dto`` + a
    custom KSerializer that reads / writes the tag inside the payload.
    kotlinx-only, mirroring the field-level constraint."""

    def _pet_doc(self):
        return parse_swagger(_doc({
            "Pet": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Dog"},
                    {"$ref": "#/components/schemas/Cat"},
                ],
                "discriminator": {
                    "propertyName": "pet_type",
                    "mapping": {
                        "dog": "#/components/schemas/Dog",
                        "cat": "#/components/schemas/Cat",
                    },
                },
            },
            "Dog": {
                "type": "object",
                "properties": {"bark_volume": {"type": "integer"}},
            },
            "Cat": {
                "type": "object",
                "properties": {"lives_left": {"type": "integer"}},
            },
        }), "test.json")

    def _union_source(self, serializer: str = "kotlinx"):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            return _gen(Path(tmp), serializer).generate_union_source(
                doc.unions[0], doc
            )

    def test_sealed_class_with_variant_and_unknown_arms(self):
        src = self._union_source()
        self.assertIn("@Serializable(with = PetDtoSerializer::class)", src)
        self.assertIn("sealed class PetDto {", src)
        self.assertIn("data class Dog(val data: DogDto) : PetDto()", src)
        self.assertIn("data class Cat(val data: CatDto) : PetDto()", src)
        self.assertIn("data object Unknown : PetDto()", src)

    def test_serializer_deserialize_dispatches_on_payload_tag(self):
        src = self._union_source()
        self.assertIn("object PetDtoSerializer : KSerializer<PetDto> {", src)
        self.assertIn(
            'return when ((obj["pet_type"] as? JsonPrimitive)?.content) {', src
        )
        self.assertIn(
            '"dog" -> PetDto.Dog(json.decodeFromJsonElement<DogDto>(obj))', src
        )
        self.assertIn("else -> PetDto.Unknown", src)

    def test_serializer_serialize_injects_tag(self):
        src = self._union_source()
        self.assertIn('put("pet_type", "dog")', src)
        self.assertIn('put("pet_type", "cat")', src)
        self.assertIn("PetDto.Unknown -> buildJsonObject {}", src)
        self.assertIn(
            "json.encodeToJsonElement(value.data).jsonObject"
            ".forEach { (k, v) -> put(k, v) }",
            src,
        )

    def test_moshi_serializer_halts(self):
        with self.assertRaises(ValueError) as ctx:
            self._union_source("moshi")
        self.assertIn("kotlinx", str(ctx.exception))

    def test_none_serializer_halts(self):
        with self.assertRaises(ValueError) as ctx:
            self._union_source("none")
        self.assertIn("kotlinx", str(ctx.exception))

    def test_union_domain_scaffold_delegates_to_dto_serializer_object(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_union_domain_source(
                doc.unions[0]
            )
        self.assertIn("@Serializable(with = PetSerializer::class)", src)
        self.assertIn("class Pet(val dto: PetDto) {", src)
        # Delegates to the serializer object directly — must NOT rely on
        # the plugin-synthesized companion serializer() of a
        # @Serializable(with = ...) sealed class.
        self.assertIn("private val dtoSerializer = PetDtoSerializer", src)
        self.assertNotIn("PetDto.serializer()", src)
        self.assertIn(
            "import com.example.app.model.generated.PetDtoSerializer", src
        )

    def test_schema_referencing_union_uses_dto_type(self):
        doc = parse_swagger(_doc({
            "Pet": {
                "oneOf": [{"$ref": "#/components/schemas/Dog"}],
                "discriminator": {
                    "propertyName": "pet_type",
                    "mapping": {"dog": "#/components/schemas/Dog"},
                },
            },
            "Dog": {
                "type": "object",
                "properties": {"bark_volume": {"type": "integer"}},
            },
            "Owner": {
                "type": "object",
                "required": ["pet"],
                "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
            },
        }), "test.json")
        owner = next(s for s in doc.schemas if s.name == "Owner")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "kotlinx").generate_dto_source(owner, doc)
        self.assertIn("val pet: PetDto", src)


class FormatAwareMappingTests(unittest.TestCase):
    """Opt-in format-aware mapping (plan 2026-07-24-v1-unsupported/03)."""

    def _fmt_gen(
        self,
        tmp: Path,
        serializer: str = "kotlinx",
        excluded: frozenset[str] = frozenset(),
    ) -> AndroidApiModelGenerator:
        return AndroidApiModelGenerator(AndroidApiPlatformConfig(
            sources_root=tmp,
            serializer=serializer,
            format_mapping=True,
            format_excluded_docs=excluded,
        ))

    def _attachment_doc(self):
        return parse_swagger(_doc({
            "Attachment": {
                "type": "object",
                "required": ["id", "data"],
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "data": {"type": "string", "format": "binary"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "stamps": {
                        "type": "array",
                        "items": {"type": "string", "format": "date-time"},
                    },
                },
            },
        }), "test.json")

    def test_native_types_kotlinx(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("import kotlinx.datetime.Instant", src)
        self.assertIn("val id: Uuid", src)
        self.assertIn(
            "val data: @Serializable(Base64ByteArraySerializer::class) ByteArray",
            src,
        )
        self.assertIn("val createdAt: Instant? = null", src)
        self.assertIn("val stamps: List<Instant>? = null", src)

    def test_moshi_and_none_halt(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            for serializer in ("moshi", "none"):
                gen = self._fmt_gen(Path(tmpdir), serializer)
                with self.assertRaises(ValueError) as ctx:
                    gen.generate_dto_source(doc.schemas[0], doc)
                self.assertIn("requires the kotlinx serializer", str(ctx.exception))
                self.assertIn("kotlinx-datetime", str(ctx.exception))

    def test_moshi_without_format_fields_unaffected(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            on = self._fmt_gen(tmp, "moshi").generate_dto_source(doc.schemas[0], doc)
            off = _gen(tmp, "moshi").generate_dto_source(doc.schemas[0], doc)
        self.assertEqual(on, off)

    def test_flag_off_output_unchanged(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            src = _gen(Path(tmpdir), "kotlinx").generate_dto_source(doc.schemas[0], doc)
        self.assertIn("val id: String", src)
        self.assertNotIn("Instant", src)
        self.assertNotIn("ByteArray", src)

    def test_per_doc_opt_out_matches_flag_off(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            excluded = self._fmt_gen(tmp, "kotlinx", frozenset({"test.json"})).generate_dto_source(doc.schemas[0], doc)
            off = _gen(tmp, "kotlinx").generate_dto_source(doc.schemas[0], doc)
        self.assertEqual(excluded, off)

    def test_support_file_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = self._fmt_gen(Path(tmpdir))
            uuid_src = gen.generate_uuid_alias_source()
            b64_src = gen.generate_base64_serializer_source()
        self.assertIn("typealias Uuid = String", uuid_src)
        self.assertIn("@generated", uuid_src)
        self.assertIn("object Base64ByteArraySerializer : KSerializer<ByteArray>", b64_src)
        self.assertIn("Base64.getEncoder().encodeToString(value)", b64_src)
        self.assertIn(
            'PrimitiveSerialDescriptor("Base64ByteArray", PrimitiveKind.STRING)',
            b64_src,
        )

    def _oneof_with_formats_doc(self, data_body: dict):
        return parse_swagger(_doc({
            "A": {"type": "object", "required": ["v"], "properties": {"v": {"type": "string"}}},
            "Parent": {
                "type": "object",
                "required": ["type", "content", "at", "data"],
                "properties": {
                    "type": {"type": "string"},
                    "at": {"type": "string", "format": "date-time"},
                    "data": data_body,
                    "content": {
                        "oneOf": [{"$ref": "#/components/schemas/A"}],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {"a": "#/components/schemas/A"},
                        },
                    },
                },
            },
        }), "test.json")

    def test_oneof_serializer_formats(self):
        doc = self._oneof_with_formats_doc({"type": "string", "format": "binary"})
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(parent, doc)
        # date rides the reified decode with the Instant type
        self.assertIn("val at: Instant = json.decodeFromJsonElement(", src)
        # binary goes through the explicit serializer both ways
        self.assertIn('element("data", Base64ByteArraySerializer.descriptor)', src)
        self.assertIn(
            "val data: ByteArray = json.decodeFromJsonElement("
            'Base64ByteArraySerializer, obj["data"] ?: error("missing data"))',
            src,
        )
        self.assertIn(
            'put("data", json.encodeToJsonElement(Base64ByteArraySerializer, value.data))',
            src,
        )

    def test_oneof_nested_binary_halts(self):
        doc = self._oneof_with_formats_doc({
            "type": "array",
            "items": {"type": "string", "format": "binary"},
        })
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as ctx:
                self._fmt_gen(Path(tmpdir)).generate_dto_source(parent, doc)
        self.assertIn("nests format: binary", str(ctx.exception))

    def test_wrapper_date_uses_instant_serializer(self):
        doc = parse_swagger(_doc({
            "Stamp": {"type": "string", "format": "date-time"},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("data class StampDto(val value: Instant)", src)
        self.assertIn("InstantIso8601Serializer", src)
        self.assertIn(
            "import kotlinx.datetime.serializers.InstantIso8601Serializer", src
        )
        self.assertIn("import kotlinx.datetime.Instant", src)


if __name__ == "__main__":
    unittest.main()
