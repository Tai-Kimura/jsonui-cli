# frozen_string_literal: true

module JsonUIShared
  # Helpers for responsive layout variant files (`home@regular.json`).
  #
  # A variant is a sibling of a base screen layout whose stem is
  # `<base>@<sizeClass>`; it replaces the WHOLE tree when the runtime
  # size class matches (no partial merge). The v1 file-suffix vocabulary
  # is compact / medium / regular only — landscape and combined forms
  # stay inline-`responsive` territory. Constraint validation lives in
  # `jui build` (_check_variant_constraints); the tools only need to
  # recognize variants, exclude them from independent screen generation
  # and attach them to their base.
  #
  # Mirrors jui_tools/jui_cli/core/layout_variant.py — keep in sync.
  #
  # Usage:
  #   LayoutVariant.variant?('home@regular')        # => true
  #   LayoutVariant.split('home@regular')           # => ['home', 'regular']
  #   LayoutVariant.split('home')                   # => ['home', nil]
  #   LayoutVariant.variants_for('/x/home.json')    # => {'regular' => '/x/home@regular.json'}
  #
  module LayoutVariant
    VALID_VARIANT_CLASSES = %w[compact medium regular].freeze

    # Split a layout file stem into [base, size_class]; size_class is nil
    # for base files. Splits on the LAST '@'.
    def self.split(stem)
      return [stem, nil] unless stem.include?('@')

      idx = stem.rindex('@')
      [stem[0...idx], stem[(idx + 1)..]]
    end

    # True when the stem (or file path) carries an '@' variant suffix.
    # Invalid suffixes still count — exclusion must not depend on the
    # gate having accepted the file.
    def self.variant?(path_or_stem)
      File.basename(path_or_stem.to_s, '.json').include?('@')
    end

    # Existing variant files for a base layout path, keyed by size class
    # (valid classes only, resolution order compact → medium → regular).
    def self.variants_for(base_path)
      dir = File.dirname(base_path)
      stem = File.basename(base_path, '.json')
      VALID_VARIANT_CLASSES.each_with_object({}) do |cls, found|
        candidate = File.join(dir, "#{stem}@#{cls}.json")
        found[cls] = candidate if File.exist?(candidate)
      end
    end
  end
end
