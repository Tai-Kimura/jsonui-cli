# frozen_string_literal: true

require 'spec_helper'
require 'compose/components/button_component'
require 'json'
require 'tmpdir'
require 'stringio'
require 'compose/compose_builder'
require 'core/stage_failures'

# Handler NAME references — canon: shared/core/binding_semantics.json
# → contexts.nameRef. The Compose half of the pin measured on 2026-09-10; see
# rjui_tools/spec/react/converters/handler_name_spelling_spec.rb for the
# history. camelCase event attributes take the binding form only.
RSpec.describe 'handler name spelling (compose)' do
  def on_click_line(value)
    imports = Set.new
    code = KjuiTools::Compose::Components::ButtonComponent.generate(
      { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'onClick' => value }, 0, imports
    )
    code.lines.grep(/onClick/).first.to_s
  end

  it 'onClick with the binding form invokes the named handler' do
    expect(on_click_line('@{handleTap}')).to include('data.handleTap?.invoke()')
  end

  it 'onClick with a bare name is not an invocation' do
    line = on_click_line('handleTap')
    expect(line).not_to include('invoke()')
    expect(line).to include('ERROR')
  end

  # The lowercase onclick, on the build path (LayoutValidator.drop_bound_onclick!).
  def built(attr, value)
    JsonUI::StageFailures.clear!
    Dir.mktmpdir('kjui_onclick') do |dir|
      Dir.chdir(dir) do
        path = File.join(dir, 'probe.json')
        File.write(path, JSON.generate('type' => 'View', 'id' => 'root', 'child' => [
                                         { 'data' => [{ 'name' => 'handleTap', 'class' => '(() -> Unit)?' }] },
                                         { 'type' => 'Button', 'id' => 'b', 'text' => 'x', attr => value }
                                       ]))
        err = StringIO.new
        orig = $stderr
        $stderr = err
        begin
          KjuiTools::Compose::ComposeBuilder.new.build_file(path)
        ensure
          $stderr = orig
        end
        [Dir.glob(File.join(dir, '**', '*GeneratedView.kt')).map { |f| File.read(f) }.join("\n"), err.string]
      end
    end
  end

  it 'lowercase onclick with the binding form is not an invocation, and says so once' do
    kotlin, err = built('onclick', '@{handleTap}')
    expect(kotlin).not_to include('handleTap')
    expect(err.scan("'onclick' takes a bare handler name, not a binding (@{handleTap}); write a binding as onClick. Ignored.").size).to eq(1)
  end

  it 'lowercase onclick with a bare name and onClick with a binding still invoke' do
    expect(built('onclick', 'handleTap').first).to include('data.handleTap?.invoke()')
    kotlin, err = built('onClick', '@{handleTap}')
    expect(kotlin).to include('data.handleTap?.invoke()')
    expect(err).not_to include("'onclick' takes")
  end
end
