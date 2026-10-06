# frozen_string_literal: true

require 'json'
require 'tmpdir'
require_relative 'spec_helper'
require 'core/attribute_validator'

# Every conformance fixture layout, companions included (cells, embedded
# screens, variant screens), declares the attributes the SSoT marks
# `required`, checked by the same validator a consumer's `jui build` runs.
#
# The corpus is generated and never built by `jui build`, so the warning a
# consumer would see never fired for it. Until jsonui-cli 1.9.18 the generators
# emitted 168 such omissions in 89 of 1199 layouts. That meant a fixture could
# ask a renderer what it does with input the declarations forbid, and record
# the answer as a platform difference: web drew a widthless Label 1024 wide
# where Android drew 38 (ticket conformance-generators-emit-layouts-missing-
# required-attributes).
RSpec.describe 'conformance fixtures declare their required attributes' do
  CONFORMANCE_FIXTURES = File.expand_path('../../conformance/fixtures', __dir__)

  def missing_required(root)
    validator = RjuiTools::Core::AttributeValidator.new(:all)
    found = []
    walk = lambda do |node, parent_orientation, file|
      case node
      when Hash
        if node['type']
          validator.validate(node, nil, parent_orientation, file_name: file).each do |w|
            msg = w.is_a?(Hash) ? (w[:message] || w['message']).to_s : w.to_s
            found << "#{file}: #{node['type']}##{node['id']}: #{msg}" if msg.include?('Required attribute')
          end
        end
        Array(node['child'] || node['children']).each { |c| walk.call(c, node['orientation'], file) }
      when Array
        node.each { |c| walk.call(c, parent_orientation, file) }
      end
    end
    files = Dir[File.join(root, '**', '*.layout.json')].sort
    files.each { |f| walk.call(JSON.parse(File.read(f)), nil, f.delete_prefix("#{root}/")) }
    [files.size, found]
  end

  it 'finds the corpus (not a silent pass on a missing directory)' do
    expect(Dir.exist?(CONFORMANCE_FIXTURES)).to be(true), "no conformance fixtures at #{CONFORMANCE_FIXTURES}"
    expect(Dir[File.join(CONFORMANCE_FIXTURES, '**', '*.layout.json')].size).to be > 1000
  end

  it 'has no layout missing a required attribute' do
    count, found = missing_required(CONFORMANCE_FIXTURES)
    expect(count).to be > 1000
    expect(found).to eq([]), "#{found.size} required attribute(s) missing:\n#{found.first(40).join("\n")}"
  end

  # The validator sees a missing width on a node shaped like the old `after`
  # Label: the probe is alive.
  it 'reports a missing width on a widthless Label (control)' do
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'x.layout.json'), JSON.generate(
        { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
          'orientation' => 'vertical', 'child' => [{ 'type' => 'Label', 'id' => 'after', 'text' => 'After' }] }
      ))
      _, found = missing_required(dir)
      expect(found.join).to include("Required attribute 'width'")
    end
  end
end
