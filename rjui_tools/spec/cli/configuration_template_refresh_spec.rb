# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'digest'
require 'json'
require 'tmpdir'
require_relative '../../lib/cli/commands/build_command'

# An app's copy of the Configuration template (src/lib/jsonui/Configuration.ts)
# was written once and never again: an app kept the FontSpec it was first
# given, with no Configuration.Font.family and no scaling / maxScale — which
# the spread of a text that declares fontScaling passes, and tsc rejects
# (P1, ticket jui-font-provider-not-reached-without-font-attributes-android-web).
# The orchestrator's ruling 2026-11-14: a copy that is byte for byte a template
# rjui wrote before is the tool's and rjui build replaces it; any other copy is
# the app's and stays, with one INFO line (not a warning).
RSpec.describe 'rjui build refreshes an unchanged Configuration template' do
  let(:old_copy) { File.binread(File.expand_path('../fixtures/configuration_templates/Configuration.ts.27d48ac', __dir__)) }
  let(:template) { File.binread(File.expand_path('../../lib/react/templates/Configuration.ts', __dir__)) }
  let(:history) { JSON.parse(File.read(File.expand_path('../../lib/react/configuration_template_history.json', __dir__))) }

  # Runs ensure_configuration_template in an app whose copy holds `content`
  # (none: no copy). Returns the copy afterwards and the INFO lines.
  def ensure_with(content)
    Dir.mktmpdir('rjui_configuration') do |dir|
      Dir.chdir(dir) do
        File.write('rjui.config.json', JSON.generate('typescript' => true))
        FileUtils.mkdir_p('src/lib/jsonui')
        File.binwrite('src/lib/jsonui/Configuration.ts', content) if content
        infos = []
        allow(RjuiTools::Core::Logger).to receive(:info) { |line| infos << line }
        allow(RjuiTools::Core::Logger).to receive(:success)
        warns = []
        allow(RjuiTools::Core::Logger).to receive(:warn) { |line| warns << line }
        RjuiTools::CLI::Commands::BuildCommand.new([]).send(:ensure_configuration_template)
        return [File.binread('src/lib/jsonui/Configuration.ts'), infos, warns]
      end
    end
  end

  it 'lists the current templates, so the next change still knows them' do
    js = File.binread(File.expand_path('../../lib/react/templates/js/Configuration.js', __dir__))
    expect(history['Configuration.ts']).to include(Digest::SHA256.hexdigest(template)),
      'the TypeScript template changed: add its sha256 to lib/react/configuration_template_history.json'
    expect(history['Configuration.js']).to include(Digest::SHA256.hexdigest(js)),
      'the JavaScript template changed: add its sha256 to lib/react/configuration_template_history.json'
  end

  it 'the fixture is the copy the apps hold (the template of 27d48ac), and it is an earlier template' do
    expect(Digest::SHA256.hexdigest(old_copy)).to start_with('27d48ac71e2b')
    expect(old_copy).not_to eq(template)
    expect(history['Configuration.ts']).to include(Digest::SHA256.hexdigest(old_copy))
  end

  it 'replaces a copy that is byte for byte an earlier template with the current one' do
    copy, infos, warns = ensure_with(old_copy)
    expect(copy).to eq(template)
    expect(infos).to be_empty
    expect(warns).to be_empty
  end

  it 'keeps a copy the app changed, and says so in one INFO line, not a warning' do
    edited = old_copy.sub('fontProvider: undefined', "fontProvider: undefined /* the app's */")
    expect(edited).not_to eq(old_copy)
    copy, infos, warns = ensure_with(edited)
    expect(copy).to eq(edited)
    expect(infos.size).to eq(1)
    expect(infos.first).to include('differs from the rjui template', 'Configuration.Font.family', 'fontScaling')
    expect(warns).to be_empty
  end

  it 'leaves the current template alone and says nothing' do
    copy, infos, = ensure_with(template)
    expect(copy).to eq(template)
    expect(infos).to be_empty
  end

  it 'writes the template when there is no copy' do
    copy, = ensure_with(nil)
    expect(copy).to eq(template)
  end

  # The point of the refresh: the spread of a text that declares fontScaling
  # passes scaling / maxScale, which the earlier copy's FontSpec does not have.
  describe 'a declared text after the refresh', :typescript_compile do
    let(:spread) { '...Configuration.Font.resolve({ size: 16, italic: false, scaling: false, maxScale: 2 })' }

    def compile_against(copy)
      spec = copy[/^export interface FontSpec\s*\{.*?\n\}/m].sub(/^export /, '')
      TypeScriptCompiler.compile(
        TypeScriptCompiler.component("    <span style={{ #{spread} }} />"),
        ambient: "#{TypeScriptCompiler::AMBIENT}\n#{spec}\n" \
                 "declare const Configuration: { Font: { resolve(spec: FontSpec): { [property: string]: string | number | undefined } } };"
      )
    end

    it 'compiles against the refreshed copy, and did not against the earlier one' do
      skip("tsc: #{TypeScriptCompiler.unavailable_reason}") if TypeScriptCompiler.unavailable_reason
      copy, = ensure_with(old_copy)
      expect(compile_against(copy).success?).to be(true)
      expect(compile_against(old_copy).success?).to be(false)
    end
  end
end
