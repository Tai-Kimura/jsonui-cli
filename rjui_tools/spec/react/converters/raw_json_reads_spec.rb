#!/usr/bin/env ruby

require_relative '../../spec_helper'

# Renderer SSoT Stage B grep gate: converter emit paths must not read
# node attributes through raw json['key'] access — attribute reads go
# through the typed extraction bridge (BaseConverter#attributes).
#
# Allowed raw reads (documented allowlist):
# - structural keys that define the layout tree, not renderable
#   attributes: type, child, children, data, include, style
#   (style is the style-file reference / legacy Blur effect fallback)
# - generator-injected internals prefixed with '_' (_overlay,
#   _parent_orientation, ...)
#
# extensions/ is consumer-owned custom converter code synced into
# projects (sync_tool preserves it) and is intentionally out of scope.
RSpec.describe 'Converter raw JSON reads (grep gate)' do
  CONVERTERS_GLOB = File.expand_path('../../../lib/react/converters/*_converter.rb', __dir__)

  ALLOWED_RAW_KEYS = %w[type child children data include style].freeze

  it 'only reads structural or _-internal keys through raw json access' do
    offenders = []

    Dir[CONVERTERS_GLOB].sort.each do |file|
      File.read(file).scan(/json\[["']([^"']+)["']\]/) do |(key)|
        next if ALLOWED_RAW_KEYS.include?(key)
        next if key.start_with?('_')

        offenders << "#{File.basename(file)}: json['#{key}']"
      end
    end

    expect(offenders).to be_empty, <<~MSG
      Raw attribute reads found in converter emit paths — route them
      through BaseConverter#attributes (typed bridge) instead:
      #{offenders.join("\n")}
    MSG
  end
end
