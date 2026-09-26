# frozen_string_literal: true

require 'json'
require_relative '../../spec_helper'
require 'react/converters/image_converter'
require 'react/converters/network_image_converter'

# An image with no contentMode draws the declared default. The default is
# declared once, in shared/core/attribute_semantics.json
# (`semantics.image.defaultContentMode`, the 2026-08-03 user ruling), and
# every path's no-contentMode drawing is bound to it here: the value is read
# from the file, so a changed ruling moves the expectation (4f ruling,
# 2026-09-26; ticket image-content-mode-default-differs-by-path).
RSpec.describe 'rjui codegen: an image with no contentMode' do
  shared_core = File.expand_path('../../../../shared/core', __dir__)
  declared = JSON.parse(File.read(File.join(shared_core, 'attribute_semantics.json'), encoding: 'UTF-8'))
                 .fetch('semantics').fetch('image').fetch('defaultContentMode')
  # The NetworkImage component the web face installs (rjui's template) takes
  # a `contentMode` prop with a default of its own.
  template = File.read(File.expand_path('../../../lib/react/templates/network_image.tsx', __dir__), encoding: 'UTF-8')
  template_default = template[/^\s*contentMode = '(\w+)',/, 1]

  config = { 'use_tailwind' => true }

  define_method(:emit) do |type, mode|
    node = { 'type' => type, 'id' => 'img', 'width' => 100, 'height' => 60 }
    node[type == 'NetworkImage' ? 'url' : 'src'] = type == 'NetworkImage' ? 'https://example.invalid/a.png' : '/images/a.png'
    node['contentMode'] = mode if mode
    klass = type == 'NetworkImage' ? RjuiTools::React::Converters::NetworkImageConverter : RjuiTools::React::Converters::ImageConverter
    klass.new(node, config).convert
  end

  it "emits for Image and CircleImage exactly what the declared default (#{declared}) emits" do
    %w[Image CircleImage].each do |type|
      expect(emit(type, nil)).to eq(emit(type, declared)), type
    end
  end

  it 'emits something else for another mode — the comparison can tell them apart' do
    other = declared.casecmp?('AspectFill') ? 'fit' : 'AspectFill'
    expect(emit('Image', other)).not_to eq(emit('Image', nil))
  end

  it "passes NetworkImage no contentMode, and the declared default emits the prop the component defaults to (#{template_default})" do
    expect(template_default).not_to be_nil, 'the template no longer declares a contentMode default'
    expect(emit('NetworkImage', nil)).not_to include('contentMode=')
    expect(emit('NetworkImage', declared)).to include(%(contentMode="#{template_default}"))
  end

  # What the arms above compare, type-checked: NetworkImage against the props
  # the template declares, so the declared default's contentMode has to be a
  # member of the template's union.
  it 'compiles what each image emits with no contentMode and with the declared default', :typescript_compile do
    emits = %w[Image CircleImage NetworkImage].flat_map { |type| [emit(type, nil), emit(type, declared)] }
    expect(TypeScriptCompiler.component(*emits)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
      declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
    TS
  end
end
