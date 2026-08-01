# frozen_string_literal: true

require 'core/attribute_validator'

# Characterization of the W3-2 unified validator behavior — the surface
# that used to diverge across {{s,k,r}}jui_tools before the shared core
# (lib/core/attribute_validator_core.rb) absorbed it. Each example pins a
# resolved divergence; the same spec (modulo module name and the Embed
# transitional flag) exists in all three toolchains.
RSpec.describe RjuiTools::Core::AttributeValidator do
  let(:validator) { described_class.new }

  it 'prefixes warnings with [id=…] context (was sjui-only)' do
    w = validator.validate({ 'type' => 'View', 'id' => 'probe_id', 'bogusAttr' => 1,
                             'width' => 10, 'height' => 10 })
    expect(w).to include("[id=probe_id] Unknown attribute 'bogusAttr' for component type 'View'")
  end

  it 'stays silent on weight when parent orientation is nil — include-file root semantics' do
    w = validator.validate({ 'type' => 'View', 'weight' => 1 }, nil, nil)
    expect(w).to be_empty
  end

  it 'accepts padding/margin-style numeric arrays of length 1/2/4 (renderers consume them)' do
    w = validator.validate({ 'type' => 'View', 'padding' => [8, 16],
                             'width' => 10, 'height' => 10 }, nil, 'vertical')
    expect(w).to be_empty
  end

  it 'still rejects edge-inset arrays of unsupported length or content' do
    w = validator.validate({ 'type' => 'View', 'padding' => [1, 2, 3],
                             'width' => 10, 'height' => 10 }, nil, 'vertical')
    expect(w.any? { |m| m.include?("'padding'") && m.include?('got array') }).to be true
  end

  it 'validates template text strictly — only a FULL-string @{…} is a binding' do
    # 'x@{g}' is template text, not a binding: the enum check still runs
    # (was skipped by rjui, which treated any string containing @{ as a binding).
    w = validator.validate({ 'type' => 'Label', 'text' => 't', 'gravity' => 'x@{g}',
                             'width' => 10, 'height' => 10 }, nil, 'vertical')
    expect(w.any? { |m| m.include?("'gravity'") && m.include?('invalid value') }).to be true

    w2 = validator.validate({ 'type' => 'Label', 'text' => 't', 'gravity' => '@{g}',
                              'width' => 10, 'height' => 10 }, nil, 'vertical')
    expect(w2.none? { |m| m.include?("'gravity'") }).to be true
  end

  it 'lets widthWeight/heightWeight substitute for required width/height (was missing in kjui)' do
    w = validator.validate({ 'type' => 'View', 'widthWeight' => 0.5, 'height' => 10 },
                           nil, 'horizontal')
    expect(w.none? { |m| m.include?("'width'") && m.include?('missing') }).to be true
  end

  it 'reports the Embed params tree grammar here (transitional react-only flag)' do
    w = validator.validate({ 'type' => 'Embed', 'screen' => 'X',
                             'params' => { 'BadKey' => 1, 'arr' => [1] },
                             'width' => 10, 'height' => 10 }, nil, 'vertical')
    expect(w.any? { |m| m.include?('camelCase') }).to be true
    expect(w.any? { |m| m.include?('binding-params-array') }).to be true
  end
end
