# frozen_string_literal: true

require 'json'

module JsonUIShared
  # An enum attribute's value by its declared spelling, case and all (4f's
  # ruling on the enum parse, 1.9.0 — as type names are): the values
  # attribute_definitions.json declares for the attribute, and its
  # valueAliases keys. The converters compared `value.downcase` against
  # lowercased names, so a spelling declared in no case ("Horizontal" for
  # "horizontal") was drawn on some paths and not others, while the
  # validator named it.
  #
  # `lowered` is what the converters' branches compare: the lowercased value
  # for a declared spelling, nil for anything else — a binding, an undeclared
  # spelling — which each branch already sends to its default. The validator
  # names an undeclared one; this does not say it again.
  #
  # Canonical copy: shared/core/enum_spelling.rb, mirrored byte-identical
  # into sjui_tools / kjui_tools / rjui_tools lib/core (the mirror specs).
  module EnumSpelling
    DEFINITIONS_PATH = File.join(__dir__, 'attribute_definitions.json')

    module_function

    # {} when the file cannot be read — a copy whose links dangle, a file
    # that is not JSON. The validator names that as a validation stage that
    # did not complete; the converters carry on (see `lowered`).
    def definitions
      @definitions ||= begin
        parsed = File.exist?(DEFINITIONS_PATH) ? JSON.parse(File.read(DEFINITIONS_PATH, encoding: 'UTF-8')) : {}
        parsed.is_a?(Hash) ? parsed : {}
      rescue JSON::ParserError
        {}
      end
    end

    # The spellings `attribute` accepts on `section`: the section's own
    # declaration, else common's, else — a section no enum is declared on
    # (a synonym spelling, a helper shared by several types) — every
    # section's that declares one; empty only when no section does.
    #
    # `attribute` is a name, or a path to an enum declared INSIDE an
    # object-typed attribute: %w[underline lineStyle],
    # %w[highlightAttributes textAlign], %w[partialAttributes textAlign]
    # (through an array's items) — the spellings the generator publishes as
    # `<Section>Attributes.<Parent>.<Name>.declaredSpellings`.
    def declared(section, attribute)
      path = Array(attribute).map(&:to_s)
      [section, 'common'].each do |name|
        spellings = spellings_of(entry_at(definitions[name.to_s], path))
        return spellings if spellings
      end
      # `map` + `compact`, not `filter_map`: consumers run the tools on the
      # system Ruby 2.6, which has no filter_map.
      definitions.values.map { |sec| spellings_of(entry_at(sec, path)) }.compact.flatten.uniq
    end

    def entry(section_definitions, attribute)
      section_definitions.is_a?(Hash) ? section_definitions[attribute.to_s] : nil
    end

    # The declaration at `path` inside a section: the attribute, then each
    # property below it, through an array's items.
    def entry_at(section_definitions, path)
      node = entry(section_definitions, path.first)
      path.drop(1).each do |key|
        node = node['items'] if node.is_a?(Hash) && !node['properties'].is_a?(Hash) && node['items'].is_a?(Hash)
        properties = node.is_a?(Hash) ? node['properties'] : nil
        node = properties.is_a?(Hash) ? properties[key] : nil
      end
      node
    end

    def spellings_of(entry)
      return nil unless entry.is_a?(Hash) && entry['enum'].is_a?(Array)

      (entry['enum'] + (entry['valueAliases'] || {}).keys).map(&:to_s).uniq
    end

    # Without the definitions no spelling can be judged: the value is read
    # as it was before 1.9.0, lowercased, rather than every enum in the
    # build falling to its default — the build already names the missing
    # file as a stage that did not complete.
    def lowered(value, section, attribute)
      return nil unless value.is_a?(String)
      return value.downcase if definitions.empty?
      return nil unless declared(section, attribute).include?(value)

      value.downcase
    end
  end
end
