# frozen_string_literal: true

require 'tmpdir'
require 'open3'
require_relative '../spec_helper'
require 'react/react_generator'
require 'cli/commands/build_command'
require_relative '../support/typescript_compiler'

# `scrollAnimated` on the web: the `animated` argument of
# scrollCollectionToCell (scrollCollectionToItem until jsonui-cli 1.9.0). A literal false jumps, absent or true animates (the
# declared default), and a binding decides at run time — true only when the
# bound value is true, the reading sjui (`(data.x ?? false)`) and kjui
# (`(data.x ?: false)`) give an unset bound value. Until 1.9.0 (measured on
# 46a54fc3, 2026-09-26) a binding was read as `true`: the collection animated
# whatever the data said. Ticket
# collection-attributes-declared-but-not-drawn-on-some-paths.
#
# The tsc arm checks the whole generated file against the declarations tsc
# derives from the helper `rjui build` emits (BuildCommand#
# emit_collection_scroll_helper), and a data model whose bound value is
# `boolean | undefined` — what a Bool declared without a default is.
RSpec.describe 'rjui Collection: scrollAnimated' do
  def generate(value)
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'cellClasses' => ['RowCell'],
             'scrollTo' => '@{target}' }
    node['scrollAnimated'] = value unless value == :absent
    Dir.mktmpdir('rjui_anim') do |dir|
      Dir.chdir(dir) do
        %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
        config = RjuiTools::Core::ConfigManager.load_config.merge('typescript' => true)
        RjuiTools::React::ReactGenerator.new(config).generate('Probe', { 'type' => 'View', 'id' => 'root', 'child' => [node] })
      end
    end
  end

  def animated_arg(tsx)
    # The keys argument (collectionCellKeys(…) since jsonui-cli 1.9.0 hands
    # them with no cellIdProperty too) is not this arm's subject.
    tsx[/scrollCollectionToCell\(listRef\.current, "list", data\.target, (?:null|collectionCellKeys\(.*?, null\)), '\w+', (.+), false\)/, 1] or raise "no scroll call in\n#{tsx}"
  end

  it 'absent and true animate, a literal false jumps, a binding is true only when the bound value is' do
    expect(animated_arg(generate(:absent))).to eq('true')
    expect(animated_arg(generate(true))).to eq('true')
    expect(animated_arg(generate(false))).to eq('false')
    expect(animated_arg(generate('@{animated}'))).to eq('(data.animated) === true')
    expect(animated_arg(generate('@{animated ?? true}'))).to eq('(data.animated ?? true) === true')
  end

  it 'a bound value decides: true animates; false and unset jump (evaluated as emitted)' do
    arg = animated_arg(generate('@{animated}'))
    script = [true, false, nil].map { |v| "{ const data = { animated: #{v.nil? ? 'undefined' : v} }; console.log(#{arg}); }" }.join("\n")
    out, status = Open3.capture2e('node', '-e', script)
    skip 'node is not on PATH' unless status.exited?
    expect(out.split).to eq(%w[true false false])
  end

  def helper_declarations
    Dir.mktmpdir('rjui_helper') do |dir|
      command = RjuiTools::CLI::Commands::BuildCommand.allocate
      command.instance_variable_set(:@config, { 'generated_directory' => dir, 'typescript' => true })
      allow(RjuiTools::Core::Logger).to receive(:success)
      command.send(:emit_collection_scroll_helper)
      _, status = Open3.capture2e(TypeScriptCompiler.tsc_path, '--declaration', '--emitDeclarationOnly', '--target', 'ES2020',
                                  '--outDir', dir, File.join(dir, 'collectionScroll.ts'))
      raise 'tsc could not declare the helper' unless status.success?

      File.read(File.join(dir, 'collectionScroll.d.ts')).gsub('export declare ', 'export ')
    end
  end

  it 'the generated file type-checks, with the bound value boolean | undefined' do
    skip "tsc: #{TypeScriptCompiler.unavailable_reason}" if TypeScriptCompiler.unavailable_reason

    tsx = generate('@{animated}')
    ambient = <<~TS
      #{TypeScriptCompiler::AMBIENT.sub('declare const React: any;', '')}
      declare module 'react' { const React: any; export default React; export function useRef<T>(v: T): { current: T }; export const useEffect: any; }
      declare module '@/generated/data/ProbeData' {
        export type ProbeData = { rows?: { sections: { cells?: { data: unknown[] } }[] }; target?: number; animated?: boolean };
        export const createProbeData: () => ProbeData;
      }
      declare module '@/generated/data/RowCellData' { export type RowCellData = Record<string, unknown>; }
      declare module '@/generated/components/RowCell' { const C: (props: any) => any; export default C; }
      declare module '@/generated/collectionScroll' { #{helper_declarations} }
    TS
    expect(tsx).to compile_as_typescript.with_ambient(ambient)
  end
end
