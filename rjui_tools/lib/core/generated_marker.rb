# frozen_string_literal: true

# Helpers that produce the "DO NOT EDIT" header/footer for auto-generated
# files written by rjui_tools.
#
# Keep the wording in sync with:
#   - jui_tools/jui_cli/core/generated_marker.py  (Python counterpart)
#   - sjui_tools/lib/core/generated_marker.rb
#   - kjui_tools/lib/core/generated_marker.rb
#
# Why:
#   1. Human contributors see a clear warning before editing.
#   2. LLM/Agent tools (Claude Code etc.) detect the tag and refuse to edit.
#   3. CI (`jui lint-generated`) can verify the tag is present on every
#      file in a generated output directory.

module RjuiTools
  module Core
    module GeneratedMarker
      SENTINEL       = "@generated"
      AGENT_WARNING  = "LLM/Agent: you MUST NOT modify this file."
      HUMAN_WARNING  = "Any manual edits will be OVERWRITTEN on next generation."
      END_LINE       = "END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE"

      module_function

      # Return a multi-line comment banner suitable for TS/JS/Swift/Kotlin.
      def comment_header(source:, generator:, prefix: "//")
        lines = [
          "╔══════════════════════════════════════════════════════════════════╗",
          "║  #{SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT",
          "║  Source:    #{source}",
          "║  Generator: #{generator}",
          "║  #{HUMAN_WARNING}",
          "║  #{AGENT_WARNING}",
          "╚══════════════════════════════════════════════════════════════════╝",
        ]
        lines.map { |l| "#{prefix} #{l}" }.join("\n")
      end

      # One-line closing marker.
      def comment_footer(prefix: "//")
        "#{prefix} ══ #{END_LINE} ══"
      end

      # XML comment banner (kept for API parity with sibling modules).
      def xml_header(source:, generator:)
        [
          "<!--",
          "  #{SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT",
          "  Source:    #{source}",
          "  Generator: #{generator}",
          "  #{HUMAN_WARNING}",
          "  #{AGENT_WARNING}",
          "-->",
        ].join("\n")
      end

      def xml_footer
        "<!-- ══ #{END_LINE} ══ -->"
      end

      # Return a hash suitable for embedding as the top-level ``_generated``
      # key in a JSON dict.
      def json_marker(source:, generator:)
        {
          "sentinel"     => SENTINEL,
          "source"       => source,
          "generator"    => generator,
          "doNotEdit"    => true,
          "humanWarning" => HUMAN_WARNING,
          "agentWarning" => AGENT_WARNING,
        }
      end
    end
  end
end
