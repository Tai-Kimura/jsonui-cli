# frozen_string_literal: true

require 'fileutils'
require 'set'
require 'tmpdir'
require 'compose/app_component_dynamic_check'

# Converters standing in for an app's (components/extensions).
module DynamicCheckProbes
  # Applies nothing itself (the scaffold).
  class Plain
    def self.generate(_json, _depth, _imports, _parent)
      'ProbePlain(modifier = Modifier)'
    end
  end

  # Passes the node's onLongPress to its own composable (a chat bubble's kind).
  class Presses
    def self.generate(json, _depth, _imports, _parent)
      "ProbePresses(onLongPress = { data.#{json['onLongPress'][2..-2]}?.invoke() })"
    end
  end

  # Applies the node's onLongPress as a modifier stage (a markdown text's kind).
  class PressesByModifier
    def self.generate(json, _depth, _imports, _parent)
      "ProbeByModifier(\n    modifier = Modifier\n        .pointerInput(Unit) {\n" \
        "            data.#{json['onLongPress'][2..-2]}?.invoke()\n        }\n)"
    end
  end

  # The same stage written on one line.
  class TapsByModifierInline
    def self.generate(json, _depth, _imports, _parent)
      "ProbeInline(modifier = Modifier.clickable { data.#{json['onClick'][2..-2]}?.invoke() })"
    end
  end
end

# kjui build compares what Debug (KotlinJsonUI Dynamic) draws for the app's
# own components with what it draws itself, from the project's files, and
# names what differs; it rewrites nothing.
RSpec.describe 'kjui build: the app components Debug and release draw differently' do
  around do |example|
    Dir.mktmpdir('kjui_dynamic_check') do |dir|
      @dir = dir
      @dynamic = File.join(dir, 'app/src/debug/kotlin/com/example/app/dynamic')
      FileUtils.mkdir_p(File.join(@dynamic, 'components/extensions'))
      example.run
    end
  end

  let(:config) { { '_config_dir' => @dir, 'source_directory' => 'app/src/main', 'package_name' => 'com.example.app' } }
  let(:converters) do
    { 'ProbePlain' => DynamicCheckProbes::Plain, 'ProbePresses' => DynamicCheckProbes::Presses,
      'ProbeByModifier' => DynamicCheckProbes::PressesByModifier, 'ProbeInline' => DynamicCheckProbes::TapsByModifierInline }
  end

  def registry(*types)
    cases = types.map { |t| "            \"#{t}\" -> {\n                true\n            }\n" }.join
    File.write(File.join(@dynamic, 'DynamicComponentRegistry.kt'),
               "object DynamicComponentRegistry {\n    fun createCustomComponent(type: String): Boolean {\n        return when (type) {\n#{cases}            else -> false\n        }\n    }\n}\n")
  end

  def component(type, body)
    File.write(File.join(@dynamic, "components/extensions/Dynamic#{type}Component.kt"), body)
  end

  def said(mappings)
    KjuiTools::Compose::AppComponentDynamicCheck.warnings(config, mappings: mappings, converter_class: ->(t) { converters[t] })
  end

  it 'names a type release draws that Dynamic does not register, and one registered that no converter draws' do
    registry('ProbePlain', 'ShimmerText', 'home')
    lines = said(%w[ProbePlain ProgressBar])
    expect(lines).to include("'ProgressBar' is drawn by the app in release but not registered for Dynamic — Debug draws the built-in 'Progress'")
    expect(lines).to include(a_string_starting_with("'ShimmerText' is registered for Dynamic but no converter draws it"))
    expect(lines.join).not_to include("'ProbePlain'") # in both (control)
    expect(lines.join).not_to include("'home'") # a screen g view registers
  end

  it 'says nothing for a project with no Dynamic registry' do
    expect(said(%w[ProgressBar])).to eq([])
  end

  it 'names a Dynamic component that reads the onClick buildModifier also applies, and not one that hands it off' do
    registry('ProbePlain')
    reads = "val onClick = json.get(\"onClick\")\nval modifier = ModifierBuilder.buildModifier(json, data)\n"
    component('ProbePlain', reads)
    expect(said(%w[ProbePlain])).to eq(["Dynamic component 'ProbePlain' reads the node's onClick itself, and ModifierBuilder.buildModifier applies it too — " \
                                        'Debug may call it twice. Pass handles = setOf("onClick") to buildModifier.'])
    component('ProbePlain', reads.sub('buildModifier(json, data)', 'buildModifier(json, data, handles = setOf("onClick"))'))
    expect(said(%w[ProbePlain])).to eq([])
  end

  it "names a Dynamic component that leaves to buildModifier a handler its converter passes to the component's own composable" do
    registry('ProbePresses', 'ProbePlain')
    component('ProbePresses', "val modifier = ModifierBuilder.buildModifier(json, data)\n")
    component('ProbePlain', "val modifier = ModifierBuilder.buildModifier(json, data)\n")
    expect(said(%w[ProbePresses ProbePlain])).to eq(["'ProbePresses': its converter passes onLongPress to the component's own composable, and its Dynamic component leaves it to " \
                                                      "ModifierBuilder.buildModifier — Debug applies it on the component's modifier, release where the component puts it."])
  end

  it 'does not name one whose converter applies the handler as a modifier stage, as buildModifier does — on its own lines or on one' do
    registry('ProbeByModifier', 'ProbeInline')
    component('ProbeByModifier', "val modifier = ModifierBuilder.buildModifier(json, data)\n")
    component('ProbeInline', "val modifier = ModifierBuilder.buildModifier(json, data)\n")
    expect(said(%w[ProbeByModifier ProbeInline])).to eq([])
  end

  it 'names a file it cannot read instead of skipping it' do
    registry('ProbePlain')
    File.binwrite(File.join(@dynamic, 'components/extensions/DynamicProbePlainComponent.kt'), "\xFF\xFE buildModifier(".b)
    expect(said(%w[ProbePlain])).to contain_exactly(a_string_starting_with("Could not read #{File.join(@dynamic, 'components/extensions/DynamicProbePlainComponent.kt')} (it is not UTF-8)"))
  end
end
