# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'

# The refusal has to sit on the path `jui build` takes.
#
# The first cut put it in `validate_json_tree`, which only `convert_file`
# calls and only the `convert` command calls that. `jui build` uses
# `convert_json_to_view`, so on iOS the shared checks never ran: neither the
# cellClasses rule nor the binding-where-undeclared rule, and the screen came
# back as `NoMethodError: undefined method 'each' for String` from whichever
# converter touched it first. This pins the entry point, not the rule.
RSpec.describe 'a layout refused on the jui build path' do
  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('blocking_layout') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def layout(name, body)
    path = File.join(dir, "#{name}.json")
    File.write(path, JSON.generate(body))
    path
  end

  it 'returns nil and records the layout, naming the cause' do
    path = layout('sample', 'type' => 'Collection', 'id' => 'c', 'sections' => '@{secs}')

    expect(converter.convert_json_to_view(path)).to be_nil

    entries = JsonUI::StageFailures.entries
    expect(entries.size).to eq(1)
    expect(entries.first[:stage]).to eq('layout')
    expect(entries.first[:message]).to include('was not generated')
    expect(entries.first[:message]).to include('sections')
    expect(entries.first[:message]).to include('type: array')
  end

  # nil is what stops the caller writing. `update_generated_body` with a nil
  # body would rewrite the GeneratedView already on disk, so "returns nil" is
  # the property that keeps an existing file intact.
  it 'leaves a healthy layout alone' do
    path = layout('ok', 'type' => 'View', 'id' => 'root', 'child' => [])

    expect(converter.convert_json_to_view(path)).not_to be_nil
    expect(JsonUI::StageFailures.entries).to be_empty
  end

  it 'refuses only the offending layout' do
    bad = layout('bad', 'type' => 'Collection', 'id' => 'c', 'sections' => '@{secs}')
    good = layout('good', 'type' => 'View', 'id' => 'root', 'child' => [])

    expect(converter.convert_json_to_view(bad)).to be_nil
    expect(converter.convert_json_to_view(good)).not_to be_nil
    expect(JsonUI::StageFailures.entries.size).to eq(1)
  end
end
