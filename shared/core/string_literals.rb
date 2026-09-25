# frozen_string_literal: true

module JsonUIShared
  # A text a layout author wrote, as a string literal in generated source —
  # ONE escaper per target language, for every generator helper that writes
  # one (texts, hints, titles, labels, items, defaults, URLs, test tags).
  # Canonical copy in shared/core/string_literals.rb; the per-tool copies under
  # <tool>/lib/core/ stay byte-identical (each tool's shared_core_mirror_spec).
  #
  # Until 1.8.121 each helper escaped for itself, and over 30 helpers plus 70
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
