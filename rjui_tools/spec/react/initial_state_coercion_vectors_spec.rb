# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'
require 'json'
require 'open3'

require_relative '../spec_helper'
require 'react/data_model_generator'
require_relative '../../lib/cli/commands/build_command'

# initialState on web (jsonui-test-runner spec §10.3 / §10.4), held to
# shared/core/initial_state_coercion_vectors.json — a byte copy of the
# test-runner's specs/vectors/initial-state-coercion.json.
#
# The check lives in ONE place, the emitted helper's checkTestValue; the Data
# model rjui writes for a layout calls it once per declared field. So the
# vector runs twice, both EXECUTED by node (it strips the TypeScript types
# itself, node >= 22.18 / 23.6): against the helper alone, and through the
# applyTestInitialState<X>Data the generator writes for a layout whose root
# declares the vector's data — the path a real screen takes.
RSpec.describe 'initialState coercion vectors (rjui)' do
  VECTOR_PATH = File.expand_path('../../../shared/core/initial_state_coercion_vectors.json', __dir__)
  COERCION = JSON.parse(File.read(VECTOR_PATH))

  def self.node_unavailable
    out, status = Open3.capture2e('node', '-e', 'process.stdout.write(process.versions.node)')
    return 'node is not on PATH' unless status.success?

    major, minor = out.split('.').map(&:to_i)
    return "node #{out} cannot run TypeScript (needs >= 22.18)" if major < 22 || (major == 22 && minor < 18)

    nil
  rescue Errno::ENOENT
    'node is not on PATH'
  end

  def helper(typescript: true)
    RjuiTools::CLI::Commands::BuildCommand.allocate.send(:test_bridge_helper_source, typescript)
  end

  # The helper with React's two hooks replaced by a stand-in that runs an
  # effect at once and returns its cleanup — enough to execute the hook.
  REACT_STANDIN = <<~JS
    const __effects = [];
    const useRef = (v) => ({ current: v });
    const useEffect = (fn) => { const c = fn(); if (typeof c === 'function') __effects.push(c); };
    export const __unmount = () => { while (__effects.length) __effects.pop()(); };
  JS

  def runnable(source)
    source.sub("import { useEffect, useRef } from 'react';", REACT_STANDIN)
  end

  def run_node(dir, script)
    File.write(File.join(dir, 'run.mjs'), script)
    out, status = Open3.capture2e('node', '--no-warnings', File.join(dir, 'run.mjs'), chdir: dir)
    raise "node failed:\n#{out}" unless status.success?

    JSON.parse(out.lines.last)
  end

  def verdict(result)
    { 'applied' => result['applied'].sort, 'rejected' => result['rejected'].sort_by { |r| r['key'] } }
  end

  def expected(c)
    { 'applied' => c['expect']['applied'].sort, 'rejected' => c['expect']['rejected'].sort_by { |r| r['key'] } }
  end

  before do
    reason = self.class.node_unavailable
    skip(reason) if reason
  end

  it 'is the test-runner vector, case for case (86 cases when copied)' do
    expect(COERCION['cases'].size).to eq(86)
  end

  describe 'checkTestValue, the helper alone' do
    it 'gives every case the vector verdict (TypeScript helper, executed)' do
      Dir.mktmpdir('rjui_coercion') do |dir|
        File.write(File.join(dir, 'bridge.ts'), runnable(helper))
        File.write(File.join(dir, 'vector.json'), JSON.generate(COERCION))
        results = run_node(dir, <<~JS)
          import fs from 'fs';
          import { checkTestValue } from './bridge.ts';
          const v = JSON.parse(fs.readFileSync('vector.json', 'utf8'));
          const out = v.cases.map((c) => {
            const fields = Object.fromEntries(c.data.map((d) => [d.name, d.class]));
            const r = { applied: [], rejected: [] };
            for (const [key, value] of Object.entries(c.input)) {
              if (!Object.prototype.hasOwnProperty.call(fields, key)) { r.rejected.push({ key, reason: 'not a data field' }); continue; }
              const reason = checkTestValue(value, fields[key]);
              if (reason === null) r.applied.push(key); else r.rejected.push({ key, reason });
            }
            return r;
          });
          console.log(JSON.stringify(out));
        JS
        mismatches = COERCION['cases'].each_with_index.reject { |c, i| verdict(results[i]) == expected(c) }
        expect(mismatches.map { |c, i| [c['name'], results[i]] }).to eq([])
      end
    end

    it 'the JavaScript helper gives the same verdicts' do
      Dir.mktmpdir('rjui_coercion_js') do |dir|
        File.write(File.join(dir, 'bridge.mjs'), runnable(helper(typescript: false)))
        File.write(File.join(dir, 'vector.json'), JSON.generate(COERCION))
        results = run_node(dir, <<~JS)
          import fs from 'fs';
          import { checkTestValue } from './bridge.mjs';
          const v = JSON.parse(fs.readFileSync('vector.json', 'utf8'));
          console.log(JSON.stringify(v.cases.map((c) => Object.entries(c.input).map(([k, val]) => {
            const d = c.data.find((x) => x.name === k);
            return d ? checkTestValue(val, d.class) : 'not a data field';
          }))));
        JS
        COERCION['cases'].each_with_index do |c, i|
          reasons = results[i].compact.sort
          expect(reasons).to eq(c['expect']['rejected'].map { |r| r['reason'] }.sort), c['name']
        end
      end
    end

    it 'type-checks under --strict' do
      expect(helper).to compile_as_typescript.with_ambient(TypeScriptCompiler::TestBridge::REACT_HOOKS)
    end
  end

  # The Data model the generator writes for a root declaring the case's data,
  # written by the real pipeline (process_json_file: styles, includes, the
  # declared-field walk) into a project-shaped tree next to the helper.
  def generate_models(dir, cases)
    layouts = File.join(dir, 'Layouts')
    data_dir = File.join(dir, 'generated', 'data')
    FileUtils.mkdir_p([layouts, data_dir])
    File.write(File.join(dir, 'generated', 'jsonuiTestBridge.ts'), runnable(helper))
    # A model of a CollectionDataSource field imports the class; the check
    # never reaches it (the class is unsupported), so a stand-in will do.
    File.write(File.join(data_dir, 'CollectionDataSource.ts'), "export class CollectionDataSource {}\n")
    generator = RjuiTools::React::DataModelGenerator.allocate
    {
      :@config => { 'typescript' => true }, :@use_typescript => true, :@source_path => dir,
      :@layouts_dir => layouts, :@styles_dir => File.join(dir, 'Styles'), :@data_dir => data_dir
    }.each { |k, v| generator.instance_variable_set(k, v) }
    cases.each_with_index.map do |c, i|
      name = "case#{i}"
      file = File.join(layouts, "#{name}.json")
      File.write(file, JSON.generate({ 'type' => 'View', 'data' => c['data'], 'child' => [] }))
      allow($stdout).to receive(:puts)
      generator.send(:process_json_file, file)
      path = File.join(data_dir, "Case#{i}Data.ts")
      ts = File.read(path)
      # node resolves ESM specifiers as written; the bundlers a project uses
      # resolve the extensionless one. Only the run copy is rewritten.
      File.write(path, ts.gsub(%r{from '(\.\.?/[^'.]+)'}, "from '\\1.ts'"))
      ["Case#{i}Data", ts]
    end
  end

  describe 'applyTestInitialState<X>Data, as generated' do
    it 'gives every case the vector verdict, and sets exactly the applied keys' do
      Dir.mktmpdir('rjui_coercion_gen') do |dir|
        models = generate_models(dir, COERCION['cases'])
        File.write(File.join(dir, 'vector.json'), JSON.generate(COERCION))
        imports = models.each_with_index.map do |(type, _), i|
          "import { applyTestInitialState#{type} as a#{i} } from './generated/data/#{type}.ts';"
        end
        results = run_node(dir, <<~JS)
          import fs from 'fs';
          #{imports.join("\n")}
          const apply = [#{models.size.times.map { |i| "a#{i}" }.join(', ')}];
          const v = JSON.parse(fs.readFileSync('vector.json', 'utf8'));
          console.log(JSON.stringify(v.cases.map((c, i) => apply[i](c.input))));
        JS
        mismatches = COERCION['cases'].each_with_index.reject { |c, i| verdict(results[i]) == expected(c) }
        expect(mismatches.map { |c, i| [c['name'], results[i]] }).to eq([])
        COERCION['cases'].each_with_index do |c, i|
          expect(results[i]['vars'].keys.sort).to eq(c['expect']['applied'].sort), c['name']
          c['expect']['applied'].each { |k| expect(results[i]['vars'][k]).to eq(c['input'][k]) }
        end
      end
    end

    it 'calls checkTestValue once per declared field, with the class as the layout writes it' do
      Dir.mktmpdir('rjui_coercion_text') do |dir|
        data = [
          { 'name' => 'flag', 'class' => 'Boolean' }, { 'name' => 'age', 'class' => 'Int?' },
          { 'name' => 'tags', 'class' => 'Array(String)' }, { 'name' => 'onTap', 'class' => '(() -> Void)?' }
        ]
        _, ts = generate_models(dir, [{ 'data' => data }]).first
        expect(ts).to include('case "flag":', 'checkTestValue(value, "Boolean")', 'checkTestValue(value, "Int?")',
                              'checkTestValue(value, "Array(String)")', 'checkTestValue(value, "(() -> Void)?")')
        expect(ts.scan('checkTestValue(value,').size).to eq(4)
        expect(ts).to include("reason = 'not a data field';")
        expect(ts).to include('"flag": "Boolean"', '"age": "Int?"')
      end
    end

    it 'leaves out what the generator adds by itself (only declared data is a field)' do
      Dir.mktmpdir('rjui_coercion_decl') do |dir|
        layouts = File.join(dir, 'Layouts')
        FileUtils.mkdir_p(layouts)
        File.write(File.join(layouts, 'screen.json'), JSON.generate({
          'type' => 'View', 'data' => [{ 'name' => 'own', 'class' => 'String' }],
          'child' => [{ 'type' => 'Switch', 'id' => 'sw', 'isOn' => '@{on}' }, { 'type' => 'Button', 'onClick' => '@{tap}' }]
        }))
        generator = RjuiTools::React::DataModelGenerator.allocate
        { :@config => { 'typescript' => true }, :@use_typescript => true, :@source_path => dir,
          :@layouts_dir => layouts, :@styles_dir => File.join(dir, 'Styles'),
          :@data_dir => File.join(dir, 'data') }.each { |k, v| generator.instance_variable_set(k, v) }
        allow($stdout).to receive(:puts)
        generator.send(:process_json_file, File.join(layouts, 'screen.json'))
        ts = File.read(File.join(dir, 'data', 'ScreenData.ts'))
        expect(ts).to include("export const ScreenTestFields: Record<string, string> = {\n  \"own\": \"String\",\n};")
        expect(ts).not_to include('case "on"')
        expect(ts).not_to include('case "tap"')
      end
    end

    it 'compiles beside the real helper (--strict)' do
      Dir.mktmpdir('rjui_coercion_tsc') do |dir|
        _, ts = generate_models(dir, [{ 'data' => [
          { 'name' => 'email', 'class' => 'String' }, { 'name' => 'count', 'class' => 'Int' },
          { 'name' => 'flag', 'class' => 'Bool?' }, { 'name' => 'onTap', 'class' => '() -> Void' }
        ] }]).first
        expect(ts).to compile_as_typescript
      end
    end
  end

  describe 'useJsonUITestBridge, executed' do
    # One mount of the hook on a fake window, in a fresh module instance per
    # page load; returns what it applied and what it published.
    def mount(dir, node_env:, loads:)
      File.write(File.join(dir, 'bridge.mjs'),
                 runnable(helper(typescript: false)).gsub('process.env.NODE_ENV', JSON.generate(node_env)))
      run_node(dir, <<~JS)
        const store = new Map();
        globalThis.window = {
          sessionStorage: {
            getItem: (k) => (store.has(k) ? store.get(k) : null),
            setItem: (k, v) => store.set(k, String(v)),
          },
        };
        const WRITTEN_AT = 1000000;
        store.set('JSONUI_TEST_INITIAL_STATE', JSON.stringify({
          version: 1, launchId: 'L1', screens: { login: { email: 'a@example.com', nickname: 'x' } }, writtenAt: WRITTEN_AT,
        }));
        // The document's own clock origin: 'mount' is a document the launch
        // opened (after writtenAt), 'stale-mount' one that already existed.
        const openDocument = (origin) => Object.defineProperty(globalThis, 'performance', {
          value: { timeOrigin: origin }, configurable: true, writable: true,
        });
        const out = [];
        let bridge = await import('./bridge.mjs?load=1');
        for (const load of #{JSON.generate(loads)}) {
          if (load === 'reload') { bridge = await import('./bridge.mjs?load=' + Math.random()); continue; }
          openDocument(load === 'stale-mount' ? WRITTEN_AT - 1 : WRITTEN_AT + 1);
          let data = { email: '', count: 0 };
          const set = [];
          bridge.useJsonUITestBridge('login', data, (vars) => { set.push(vars); }, (d) => ({ ...d }),
            (values) => {
              const r = { vars: {}, applied: [], rejected: [] };
              for (const [k, v] of Object.entries(values)) {
                if (k in data) { r.vars[k] = v; r.applied.push(k); } else r.rejected.push({ key: k, reason: 'not a data field' });
              }
              return r;
            });
          out.push({ set, state: JSON.parse(JSON.stringify(window.__JSONUI_STATE__ ?? null)),
                     stored: JSON.parse(store.get('JSONUI_TEST_INITIAL_STATE')) });
          bridge.__unmount();
        }
        console.log(JSON.stringify(out));
      JS
    end

    it 'applies once after mount, removes the screen from the stored payload, publishes the receipt and data' do
      Dir.mktmpdir('rjui_bridge_dev') do |dir|
        first, second = mount(dir, node_env: 'development', loads: %w[mount mount])
        expect(first['set']).to eq([{ 'email' => 'a@example.com' }])
        expect(first['state']['login']).to eq(
          'launchId' => 'L1',
          'initialState' => { 'applied' => ['email'], 'rejected' => [{ 'key' => 'nickname', 'reason' => 'not a data field' }] },
          'data' => { 'email' => '', 'count' => 0 }
        )
        expect(first['stored']['screens']).to eq({})
        # Built again in the same launch: not applied again, the receipt stays.
        expect(second['set']).to eq([])
        expect(second['state']['login']['initialState']['applied']).to eq(['email'])
      end
    end

    it 'a document opened before the payload was written leaves it untouched; the next document takes it' do
      Dir.mktmpdir('rjui_bridge_stale') do |dir|
        stale, fresh = mount(dir, node_env: 'development', loads: %w[stale-mount reload mount])
        expect(stale['set']).to eq([])
        expect(stale['state']['login']['launchId']).to be_nil
        expect(stale['state']['login']['initialState']).to be_nil
        expect(stale['stored']['screens'].keys).to eq(['login'])
        expect(fresh['set']).to eq([{ 'email' => 'a@example.com' }])
        expect(fresh['state']['login']['initialState']['applied']).to eq(['email'])
        expect(fresh['stored']['screens']).to eq({})
      end
    end

    it 'with the gate closed (production) receives nothing and publishes nothing' do
      Dir.mktmpdir('rjui_bridge_prod') do |dir|
        first, = mount(dir, node_env: 'production', loads: %w[mount])
        expect(first['set']).to eq([])
        expect(first['state']).to be_nil
        expect(first['stored']['screens'].keys).to eq(['login'])
      end
    end
  end

  describe 'production builds (esbuild define, standing in for the consumer bundlers)' do
    before { BundlerDefine.skip_unless_available! }

    it 'the hook bodies fold away: nothing reads the payload or writes the bridge' do
      folded = BundlerDefine.fold(helper, node_env: 'production')
      hook = folded[/function useJsonUITestBridge.*\z/m]
      expect(hook).not_to include('readPayload(')
      expect(hook).not_to include('publish(')
      dev = BundlerDefine.fold(helper, node_env: 'development')[/function useJsonUITestBridge.*\z/m]
      expect(dev).to include('readPayload(', 'publish(')
    end
  end
end
