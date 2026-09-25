# frozen_string_literal: true

require 'json'
require 'open3'
require 'set'
require 'tmpdir'
require 'core/logger'
require 'compose/generators/dynamic_component_generator'
require_relative '../../support/kotlin_compiler'

# The sentence a leaf's Dynamic wrapper shows when a layout gives it children
# is the one SwiftJsonUI's LeafChildren.rejection shows on iOS: both are run
# against shared/core/leaf_children_vectors.json (SwiftJsonUI copies it into
# its test fixtures). Run, not read — the function is compiled with kotlinc
# and executed over every case, so a wording, an index or a plural that drifts
# on either side is red on that side.
#
# The check is written INTO the wrapper, not called from KotlinJsonUI: a
# library helper made the wrapper uncompilable on a face still on
# KotlinJsonUI 2.41.1 (measured 2026-09-25). Ticket
# sjui-leaf-custom-component-cannot-reject-children.
RSpec.describe 'the leaf wrapper kjui writes' do
  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  def vectors_path
    File.expand_path('../../../../shared/core/leaf_children_vectors.json', __dir__)
  end

  def wrapper(name)
    Dir.mktmpdir('kjui_leaf_msg') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        KjuiTools::Compose::Generators::DynamicComponentGenerator
          .new(name, is_container: false, attributes: { 'title' => 'String' }).send(:dynamic_template)
      end
    end
  end

  def rejection_function(kotlin)
    kotlin[/^    \/\*\* What a layout that gives this leaf children.*?^    }\n/m]
      .gsub(/^    /, '').sub('private fun', 'fun')
  end

  it 'depends on nothing KotlinJsonUI 2.41.1 lacks: no LeafChildren, only what every wrapper already calls' do
    kotlin = wrapper('Leaf')
    expect(kotlin).not_to include('LeafChildren')
    library_refs = kotlin.scan(/com\.kotlinjsonui\.[\w.]+/).uniq.sort
    expect(library_refs).to eq(%w[com.kotlinjsonui.dynamic.helpers.ModifierBuilder com.kotlinjsonui.dynamic.helpers.ResourceResolver])
  end

  def runner_source
    <<~KT
      import com.google.gson.JsonObject
      import com.google.gson.JsonParser

      #{rejection_function(wrapper('Leaf'))}
      fun main(args: Array<String>) {
          val table = JsonParser.parseString(java.io.File(args[0]).readText()).asJsonObject
          val out = com.google.gson.JsonArray()
          for (c in table.getAsJsonArray("cases")) {
              val r = leafRejection(c.asJsonObject.getAsJsonObject("component"))
              if (r == null) out.add(com.google.gson.JsonNull.INSTANCE) else out.add(r)
          }
          println(out.toString())
      }
    KT
  end

  it 'writes a refusal that compiles against Gson alone' do
    expect(runner_source).to compile_as_kotlin(:gson)
  end

  it 'says what shared/core/leaf_children_vectors.json says, case by case, when run' do
    skip "kotlinc: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason
    gson = KotlinCompiler.newest('com.google.code.gson', 'gson')
    skip 'gson is not in the Gradle cache' unless gson

    cases = JSON.parse(File.read(vectors_path))['cases']
    expect(cases.map { |c| c['expected'].nil? }.uniq).to contain_exactly(true, false)

    source = runner_source

    stdlib = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    got = Dir.mktmpdir('kjui_leaf_run') do |dir|
      file = File.join(dir, 'LeafMessage.kt')
      File.write(file, source)
      compiler_cp = [KotlinCompiler.compiler_jar, stdlib,
                     KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-reflect'),
                     KotlinCompiler.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm'),
                     KotlinCompiler.newest('org.jetbrains', 'annotations'),
                     KotlinCompiler.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
      out, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                    '-no-stdlib', '-cp', [stdlib, gson].join(':'), '-d', File.join(dir, 'out'), file)
      raise "kotlinc: #{out}" unless status.success?

      run, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', [stdlib, gson, File.join(dir, 'out')].join(':'),
                                    'LeafMessageKt', vectors_path)
      raise "run: #{run}" unless status.success?

      JSON.parse(run.lines.last)
    end
    cases.zip(got).each do |vector, result|
      expect(result).to eq(vector['expected']), vector['name']
    end
  end
end
