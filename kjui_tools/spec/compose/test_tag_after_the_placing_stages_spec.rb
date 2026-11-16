# frozen_string_literal: true

require_relative '../spec_helper'

# The testTag (with testTagsAsResourceId) comes after the stages that place
# the view — margins and offset — in every modifier chain kjui emits (ticket
# kjui-a11y-bounds-of-a-margined-view-include-its-margin). A margin is drawn
# as padding, so a tag before it made the tagged box (the resource-id bounds,
# TalkBack's focus frame) the margin-inclusive box: a 50 x 50 view at margin
# 120 reported 0..170. The order is written once per component chain, so this
# reads the source: a build_test_tag call that a build_margins / build_offset
# call of the same chain follows is a regression, caught the day a component
# is written.
RSpec.describe 'kjui codegen: the testTag sits inside the margins and the offset' do
  lib = File.expand_path('../../lib', __dir__)

  # Each build_test_tag call, and the first margins / offset call after it in
  # the same chain. The chain ends at the end of its method, at the end of
  # the branch it is in (else / elsif / end at a lower indent), or where its
  # variable is rebuilt (`modifiers = [`).
  def self.violations(source)
    lines = source.split("\n")
    found = []
    lines.each_with_index do |line, i|
      next unless line.include?('build_test_tag(')
      next if line.strip.start_with?('#') || line.include?('def self.build_test_tag')

      indent = line[/\A\s*/].length
      var = line[/\A\s*(\w+)/, 1]
      (i + 1...lines.length).each do |k|
        text = lines[k]
        stripped = text.strip
        break if text.match?(/\A\s*def /)
        break if !stripped.empty? && text[/\A\s*/].length < indent && stripped.match?(/\A(else|elsif|end)\b/)
        break if var && text.match?(/\A\s*#{Regexp.escape(var)}\s*=\s*\[/)
        next if stripped.start_with?('#')

        if (m = text.match(/build_(margins|offset)\(/))
          found << "line #{i + 1}: build_test_tag before build_#{m[1]} at line #{k + 1}"
          break
        end
      end
    end
    found
  end

  sources = Dir.glob(File.join(lib, 'compose', '**', '*.rb')).select { |f| File.read(f).include?('build_test_tag(') }

  it 'reads every chain that tags a node' do
    # The population, so a reader sees what the check covers.
    expect(sources.size).to be >= 30
  end

  sources.each do |path|
    it "#{path.delete_prefix("#{lib}/")}: no tag before a margins / offset stage" do
      expect(self.class.violations(File.read(path))).to eq([])
    end
  end

  describe 'the reader (controls)' do
    it 'finds a tag placed before the margins' do
      source = <<~RUBY
        def self.generate(json_data)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
        end
      RUBY
      expect(self.class.violations(source).size).to eq(1)
    end

    it 'passes a tag after the margins and the offset' do
      source = <<~RUBY
        def self.generate(json_data)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
        end
      RUBY
      expect(self.class.violations(source)).to eq([])
    end

    it 'stops at the end of a branch: a hidden branch tag is not judged by the other branch' do
      source = <<~RUBY
        def self.generate(json_data)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          if hidden
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
            modifiers << ".alpha(0f)"
          else
            modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          end
        end
      RUBY
      expect(self.class.violations(source)).to eq([])
    end
  end
end
