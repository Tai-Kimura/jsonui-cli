# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'

require_relative '../spec_helper'
require 'react/hook_generator'
require_relative '../../lib/cli/commands/generate_command'

# Where useJsonUITestBridge is called (jsonui-test-runner spec §10.3): every
# generated ViewModel hook, and the page scaffold — a page that does not go
# through a hook would otherwise receive no initialState and publish no
# state, and the driver fails it with "no receipt". The screen id handed over
# is the layout's (shared/core/screen_identity.json), the same one the
# screen marker carries.
RSpec.describe 'useJsonUITestBridge call sites' do
  # The declarations the hook and the page import, cut and declared here so
  # tsc reads the emitted body against the shapes the generators write.
  LOGIN_AMBIENT = <<~TS
    interface LoginData { email?: string; onEmailChange?: (value: string) => void }
    declare function createLoginData(): LoginData;
    declare function testSnapshotLoginData(data: LoginData): Record<string, unknown>;
    declare function applyTestInitialStateLoginData(values: Record<string, unknown>): JsonUITestApplyResult<LoginData>;
    declare class LoginViewModel {
      constructor(router: unknown, getData: () => LoginData, setData: (d: LoginData | ((p: LoginData) => LoginData)) => void);
      setVars(vars: Partial<LoginData>): void;
    }
    declare function useRef<T>(initial: T): { current: T };
    declare function useState<T>(initial: T): [T, (next: T | ((prev: T) => T)) => void];
    type AppRouterInstance = unknown;
    declare function useRouter(): AppRouterInstance;
    declare const Login: (props: { data: LoginData }) => JSX.Element;
  TS

  def cut_imports(source)
    source.lines.reject { |l| l.start_with?('import ', '"use client"', "'use client'") }.join
  end

  describe 'the generated ViewModel hook' do
    let(:hooks) do
      h = RjuiTools::React::HookGenerator.allocate
      h.instance_variable_set(:@framework, RjuiTools::Core::Frameworks.for({}))
      h
    end
    let(:ts) { hooks.send(:generate_typescript_hook, 'Login', { 'email' => 'string' }, {}, 'login') }
    let(:js) { hooks.send(:generate_javascript_hook, 'Login', { 'email' => 'string' }, {}, 'login') }

    it 'imports the helper and the Data module test functions' do
      expect(ts).to include('import { useJsonUITestBridge } from "@/generated/jsonuiTestBridge";')
      expect(ts).to include('testSnapshotLoginData, applyTestInitialStateLoginData } from "@/generated/data/LoginData";')
      expect(js).to include('import { useJsonUITestBridge } from "@/generated/jsonuiTestBridge";')
    end

    it 'calls it with the screen id, the raw data and the Data module functions' do
      expect(ts).to include('useJsonUITestBridge("login", data, (vars: Partial<LoginData>) => setData(prev => ({ ...prev, ...vars })), testSnapshotLoginData, applyTestInitialStateLoginData);')
      expect(js).to include('useJsonUITestBridge("login", data, (vars) => setData(prev => ({ ...prev, ...vars })), testSnapshotLoginData, applyTestInitialStateLoginData);')
    end

    it 'compiles (--strict) against the helper signature' do
      expect(cut_imports(ts)).to compile_as_typescript.with_ambient(LOGIN_AMBIENT)
    end

    it 'takes the screen id from the layout path, variant removed' do
      expect(JsonUIShared::ScreenIndex.screen_id_for_path('Layouts/pages/login@regular.json')).to eq('login')
    end
  end

  describe 'the page scaffold' do
    let(:command) do
      c = RjuiTools::CLI::Commands::GenerateCommand.allocate
      c.instance_variable_set(:@config, { 'typescript' => true })
      c
    end

    it 'calls it in both page shapes, with the layout basename as the screen id' do
      [true, false].each do |with_vm|
        page = command.send(:page_content, 'Login', with_vm, 'login')
        expect(page).to include('useJsonUITestBridge("login", data, (vars: Partial<LoginData>) => setData(prev => ({ ...prev, ...vars })), testSnapshotLoginData, applyTestInitialStateLoginData);')
        expect(cut_imports(page)).to compile_as_typescript.with_ambient(LOGIN_AMBIENT)
      end
    end

    it 'the JavaScript page drops the types from the call' do
      js = command.send(:javascript_page, command.send(:page_content, 'Login', false, 'login'), 'Login')
      expect(js).to include('useJsonUITestBridge("login", data, (vars) => setData(')
      expect(js).to include('import { createLoginData, testSnapshotLoginData, applyTestInitialStateLoginData } from')
    end
  end
end
