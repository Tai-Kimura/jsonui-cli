# frozen_string_literal: true

module KjuiTools
  module Compose
    # Which hand-held converters do not emit a testTag.
    #
    # 🚨 WHY THIS EXISTS. v1.8.56 fixed the converter TEMPLATE to emit
    # `Helpers::ModifierBuilder.build_test_tag(...)`, as every built-in
    # component does. ⚠️ A template fix does not reach converters that
    # already exist, and nothing counted them:
    #
    #     built-in components emitting build_test_tag   27 / 28
    #     one face's hand-written extensions            **0 / 8**
    #     lint or validate paths referencing it          0
    #
    # The 27/28 is what makes the 0/8 legible. On its own "none of them have
    # it" reads as a convention; beside a population that almost all has it,
    # it is a gap. So this audit reports BOTH numbers, always.
    #
    # A converter with no testTag renders a node that `By.res(id)` cannot
    # find, which is invisible until someone writes a test that needs it —
    # the failure is in a test not yet written, so nothing fails today.
    #
    # ⚠️ REPORTED, NOT ENFORCED. A converter may legitimately draw nothing
    # addressable. The exit code is not touched; the operator decides.
    module ConverterTestTagAudit
      TEST_TAG_CALL = 'build_test_tag'

      # Converters live in the face's vendored tools, beside this file.
      def self.extensions_dir(root = nil)
        base = root || File.dirname(__FILE__)
        File.join(base, 'components', 'extensions')
      end

      def self.builtins_dir(root = nil)
        base = root || File.dirname(__FILE__)
        File.join(base, 'components')
      end

      # `[missing, total]` for the converters in *dir*.
      def self.scan(dir)
        return [[], 0] unless Dir.exist?(dir)
        files = Dir.glob(File.join(dir, '*_component.rb')).sort
        missing = files.reject { |f| File.read(f).include?(TEST_TAG_CALL) }
        [missing, files.length]
      end

      # The line(s) to print, or [] when there is nothing to say.
      #
      # Silent when there are no converters at all: a project that never ran
      # `jui g converter` has nothing to be missing, and a line that fired on
      # the absence of an optional directory would print for most projects.
      def self.findings(root = nil)
        missing, total = scan(extensions_dir(root))
        return [] if total.zero? || missing.empty?

        builtin_missing, builtin_total = scan(builtins_dir(root))
        builtin_have = builtin_total - builtin_missing.length
        names = missing.map { |f| File.basename(f) }.join(', ')
        [
          "#{missing.length} of #{total} converter(s) in components/extensions " \
          "do not emit #{TEST_TAG_CALL} (#{names}). Built-in components: " \
          "#{builtin_have}/#{builtin_total} emit it. A node without a testTag " \
          "cannot be found by By.res(id), so a test that needs it fails later " \
          "rather than here. The converter template emits it from v1.8.56 — " \
          "converters generated before that keep the old shape."
        ]
      end
    end
  end
end
