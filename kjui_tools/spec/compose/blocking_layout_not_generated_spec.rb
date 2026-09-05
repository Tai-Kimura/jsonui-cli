# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/stage_failures'

# The refusal on the Android build path.
#
# `build_file` is what `jui build` drives per layout. A declaration violation
# the converters cannot survive — a binding where the declaration takes a list
# — is recorded and the file is abandoned before any Kotlin is emitted, rather
# than reaching `sections.any?` on a String.
#
# `return`, not `next`: `build_file` is a method. `next` parses there and
# raises LocalJumpError at run time, which `ruby -c` does not catch.
RSpec.describe 'a layout refused on the Android build path' do
  let(:builder) { KjuiTools::Compose::ComposeBuilder.new }
  let(:dir) { Dir.mktmpdir('kjui_blocking') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def layout(name, body)
    path = File.join(dir, "#{name}.json")
    File.write(path, JSON.generate(body))
    path
  end

  it 'records the layout and emits nothing for it' do
    path = layout('sample', 'type' => 'Collection', 'id' => 'c', 'sections' => '@{secs}')

    builder.build_file(path)

    entries = JsonUI::StageFailures.entries
    expect(entries.size).to eq(1)
    expect(entries.first[:stage]).to eq('layout')
    expect(entries.first[:message]).to include('was not generated')
    expect(entries.first[:message]).to include('sections')
  end

  # `Dir.chdir`: a healthy layout really does emit, and kjui resolves its
  # output relative to the working directory — run from the tool tree it
  # writes `app/src/main/kotlin/...` into the checkout. Measured: the first
  # cut of this spec left 14 untracked files behind. A test that dirties the
  # tree it is testing is one `git add -A` away from shipping itself.
  it 'does not record a healthy layout' do
    path = layout('ok', 'type' => 'View', 'id' => 'root', 'child' => [])
    Dir.chdir(dir) do
      begin
        builder.build_file(path)
      rescue StandardError
        # Emission needs project config this spec does not set up; what is
        # under test is that nothing was RECORDED, which happens before it.
        nil
      end
    end
    expect(JsonUI::StageFailures.entries).to be_empty
  end
end
