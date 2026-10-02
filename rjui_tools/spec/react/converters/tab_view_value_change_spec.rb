# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'

# TabView.onValueChange is called when the selected tab's value changes — a
# tap on another tab or a selectedIndex write — and not when the tab view
# first appears or the selected tab is tapped again (ruling 2026-10-02, the
# SSoT's TabView.onValueChange; as SwiftJsonUI's `.onChange(of: selection)`).
# A tab's tap only writes the selection; the file's JsonUIValueChange calls
# the handler on a change. Until jsonui-cli 1.9.6 the tab's onClick called it,
# so a second tap called it again and a selectedIndex write never did
# (measured in Chromium: [] / [1] / [1,1] / [1,1] before, [] / [1] / [1] / [1,0]
# after — appear / tap B / tap B again / write 0; ticket
# tabview-value-change-is-called-on-a-tap-not-on-a-change).
RSpec.describe 'rjui TabView: onValueChange on a change of the selection' do
  def generate(extra = {}, handler = '@{onTab}')
    tv = { 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => 'A', 'view' => 'tab_a' }, { 'title' => 'B', 'view' => 'tab_b' }] }
    tv['onValueChange'] = handler if handler
    data = [{ 'name' => 'onTab', 'class' => '(Int) -> Void' }, { 'name' => 'tab', 'class' => 'Int', 'defaultValue' => 0 }]
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [{ 'data' => data }, tv.merge(extra)] }
    RjuiTools::React::ReactGenerator.new({ 'typescript' => true }).generate('Tabs', layout, screen_id: 'tabs')
  end

  it 'a tab tap writes the selection only; JsonUIValueChange calls the handler with the selection' do
    { {} => ['setSeeded(1); data.setSelectedTabIndex?.(1);', '(data.selectedTabIndex ?? seeded)'],
      { 'selectedIndex' => '@{tab}' } => ['data.setTab?.(1)', '(data.tab ?? 0)'] }.each do |extra, (write, selection)|
      tsx = generate(extra)
      taps = tsx.scan(/onClick=\{[^\n]*\}/).join("\n")
      expect(taps).to include(write)
      expect(taps).not_to include('onTab')
      expect(tsx).to include("<JsonUIValueChange value={#{selection}} onChange={(value) => data.onTab?.(value)} />")
      expect(tsx).to include('const JsonUIValueChange =', "import React, { useState, useRef, useEffect } from 'react';") if extra.empty?
    end
  end

  it 'control: with no handler there is no JsonUIValueChange, and a tap writes the selection as before' do
    tsx = generate({}, nil)
    expect(tsx).not_to include('JsonUIValueChange')
    expect(tsx).to include('onClick={() => { setSeeded(1); data.setSelectedTabIndex?.(1); }}')
  end

  it 'writes a file that compiles, with and without a bound selectedIndex', :typescript_compile do
    [{}, { 'selectedIndex' => '@{tab}' }].each do |extra|
      body = generate(extra).lines.reject { |l| l.start_with?('import ') }.join
      expect(body).to compile_as_typescript.with_ambient(<<~TS)
        declare namespace React { type ReactNode = unknown }
        declare function useState<T>(initial: T): [T, (value: T) => void];
        declare function useRef<T>(initial: T): { current: T };
        declare function useEffect(effect: () => void, deps: unknown[]): void;
        interface TabsData { onTab?: (index: number) => void; tab?: number; setTab?: (index: number) => void;
          selectedTabIndex?: number; setSelectedTabIndex?: (index: number) => void; tabAData?: unknown; tabBData?: unknown }
        declare function createTabsData(): TabsData;
        declare function screenMarker(screenId: string): Record<string, string>;
        declare function Circle(props: { className?: string }): JSX.Element;
        declare function TabA(props: { data?: unknown }): JSX.Element;
        declare function TabB(props: { data?: unknown }): JSX.Element;
      TS
    end
  end
end
