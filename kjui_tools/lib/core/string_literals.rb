# frozen_string_literal: true

require 'json'

module JsonUIShared
  # A text a layout author wrote, as a string literal in generated source —
  # ONE escaper per target language, for every generator helper that writes
  # one (texts, hints, titles, labels, items, defaults, URLs, test tags).
  # Canonical copy in shared/core/string_literals.rb; the per-tool copies under
  # <tool>/lib/core/ stay byte-identical (each tool's shared_core_mirror_spec).
  #
  # Until 1.9.0 each helper escaped for itself, and over 30 helpers plus 70
  # inline writers disagreed (2026-09-26): Kotlin's `$` was escaped almost
  # nowhere (`"Pay $x"` became a template); in Swift `gsub('\\', '\\\\')`
  # does not double a backslash (a gsub replacement reads `\\` as one `\`), so
  # `C:\new \(total)` became a newline and an interpolation; in rjui's JSX
  # escapers a replacement "\\`" means the text BEFORE the match, so
  # "It`s" became "ItIts". Ticket
  # codegen-string-literals-are-not-escaped-for-the-target-language.
  #
  # Every escape below is the BLOCK form of gsub: a block's return value is
  # taken as is, so no backslash sequence in it is read as a back-reference.
  #
  # A text with none of a language's special characters comes out byte for
  # byte as `"text"` did before, so regenerating such a layout changes
  # nothing.
  module StringLiterals
    module_function

    SWIFT_ESCAPES = { '\\' => '\\\\', '"' => '\\"', "\n" => '\\n', "\r" => '\\r', "\t" => '\\t', "\0" => '\\0' }.freeze

    # A Swift string literal: `\` (which also keeps `\(` from interpolating),
    # `"`, and the control characters.
    def swift(text)
      "\"#{swift_body(text)}\""
    end

    # The inside of a Swift string literal, for a caller that writes the
    # quotes itself.
    def swift_body(text)
      text.to_s.gsub(/[\\"\x00-\x1f\x7f]/) do |c|
        SWIFT_ESCAPES[c] || format('\\u{%x}', c.ord)
      end
    end

    KOTLIN_ESCAPES = { '\\' => '\\\\', '"' => '\\"', '$' => '\\$', "\n" => '\\n', "\r" => '\\r', "\t" => '\\t',
                       "\b" => '\\b' }.freeze

    # A Kotlin string literal: `\`, `"`, `$` (it opens a template), and the
    # control characters.
    def kotlin(text)
      "\"#{kotlin_body(text)}\""
    end

    def kotlin_body(text)
      text.to_s.gsub(/[\\"$\x00-\x1f\x7f]/) do |c|
        KOTLIN_ESCAPES[c] || format('\\u%04x', c.ord)
      end
    end

    TS_ESCAPES = { '\\' => '\\\\', '"' => '\\"', "\n" => '\\n', "\r" => '\\r', "\t" => '\\t',
                   "\u2028" => '\\u2028', "\u2029" => '\\u2029' }.freeze

    # A TypeScript / JavaScript double-quoted string literal.
    def ts(text)
      "\"#{ts_body(text)}\""
    end

    def ts_body(text)
      text.to_s.gsub(/[\\"\x00-\x1f\x7f\u2028\u2029]/) do |c|
        TS_ESCAPES[c] || format('\\u%04x', c.ord)
      end
    end

    # A TypeScript / JavaScript single-quoted string literal.
    def ts_single(text)
      "'#{text.to_s.gsub(/[\\'\x00-\x1f\x7f\u2028\u2029]/) { |c| c == "'" ? "\\'" : (TS_ESCAPES[c] || format('\\u%04x', c.ord)) }}'"
    end

    # The inside of a template literal (between backticks): `\`, the
    # backtick, `${`, and a CR — a template literal holds a newline as it
    # is, but reads a raw CR (or CRLF) as a newline.
    def ts_template_body(text)
      text.to_s.gsub(/\\|`|\$\{|\r/) { |m| m == "\r" ? '\\r' : "\\#{m}" }
    end

    # The text an author's String default means, before any language's
    # escaping — ONE reading of the layout's spellings for the three
    # generators and the dynamic runtimes (SwiftJsonUI / KotlinJsonUI
    # DataDefaultValue), all measured against shared/core/
    # string_default_vectors.json:
    #   anything  the text as written — the CANONICAL spelling: `jui g
    #             project` writes a spec's uiVariables default this way
    #   ''        empty
    #   "…"       a literal: its escapes are JSON's (`\"` `\\` `\n` `\t`
    #             `\uXXXX`), the ones Swift, Kotlin and TypeScript share;
    #             when they do not read as JSON, the text between the quotes
    #   '…'       the text between the quotes, as written
    # `jui g project` does not write the quoted spellings.
    # Until 1.9.0 the three read `"Test"` three ways: Kotlin and TS as
    # `Test`, Swift as `""Test""` (not Swift) — then as `"Test"` with its
    # quotes; `'it''s'` became invalid TS, and a bare `Say "hi"` was written
    # unescaped into TS (ticket
    # codegen-string-literals-are-not-escaped-for-the-target-language,
    # remaining 1).
    def default_text(raw)
      text = raw.to_s
      return '' if text == "''"
      if text.length >= 2 && text.start_with?('"') && text.end_with?('"')
        # Only JSON's escapes, read two characters at a time (so `\\d` is
        # a backslash and a d): Ruby's parser takes an unknown one (`\d`)
        # and drops its backslash, which is not "as written".
        # A raw control character is not JSON either, and a lone surrogate
        # (`\udc00`) decodes to bytes that are not UTF-8 on every json
        # version measured (2.1.0 and 2.16.0) — as written, both.
        inner = text[1...-1]
        escapes = inner.scan(/\\(u\h{4}|.)/m).flatten
        return inner unless escapes.all? { |e| e.length == 5 || '"\\/bfnrt'.include?(e) }
        return inner if inner.match?(/[\x00-\x1f]/)

        begin
          decoded = JSON.parse("[#{text}]")
          return decoded.first if decoded.length == 1 && decoded.first.is_a?(String) && decoded.first.valid_encoding?
        rescue JSON::ParserError
          nil
        end
        return inner
      end
      return text[1...-1] if text.length >= 2 && text.start_with?("'") && text.end_with?("'")

      text
    end

    # What JSX text cannot hold as it is: braces and angle brackets, and an
    # HTML character reference (`&amp;`, `&#123;`), which JSX text reads as
    # the character it names. A lone `&` is text.
    JSX_TEXT_SPECIAL = /[{}<>]|&(?:#\d+|#x\h+|[A-Za-z][A-Za-z0-9]*);/.freeze

    # A text as a JSX child: as it is when nothing in it is special to JSX,
    # else as an expression holding a string literal.
    def jsx_text(text)
      text = text.to_s
      text.match?(JSX_TEXT_SPECIAL) ? "{#{ts(text)}}" : text
    end
  end
end
