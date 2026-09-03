# frozen_string_literal: true

require 'rspec/core/sandbox'

# The matcher's third state.
#
# ubuntu's setup-ruby image ships swiftc without the SwiftUI SDK, so
# `SwiftCompiler.available?` was true there and every compile failed on its
# first line with "no such module 'SwiftUI'": four label-converter examples
# red for a toolchain reason, on the 2.6 leg whose `--tag '~swift'` excluded
# nothing (the tag is :swift_compile, and it is derived onto the whole
# spec/swiftui tree, so excluding it would drop the tree). Before that, a
# machine with no swiftc at all got `success: true` back — a check that did
# not run, counted as a check that passed.
#
# What is pinned here is the STATUS an example ends in, observed by running
# one inside a sandboxed group — not that some exception is raised. A bare
# raise of SkipDeclaredInExample is rescued by the runner as a no-op and the
# example ends PASSED (the control below shows it), which is how the first
# version of this fix turned four failures into four silent passes.
RSpec.describe 'compile_as_swift' do
  # Force the probe's answers without mocks: a sandboxed run tears down the
  # mock space, so a stub set out here would not survive into the inner
  # example. Memoized answers do.
  def with_compiler(available:, swiftui:)
    saved = [:@available, :@swiftui_available].map { |v| SwiftCompiler.instance_variable_get(v) }
    SwiftCompiler.instance_variable_set(:@available, available)
    SwiftCompiler.instance_variable_set(:@swiftui_available, swiftui)
    yield
  ensure
    SwiftCompiler.instance_variable_set(:@available, saved[0])
    SwiftCompiler.instance_variable_set(:@swiftui_available, saved[1])
  end

  # Run one example body in a sandbox and hand back its execution result.
  def run_example(&body)
    result = nil
    RSpec::Core::Sandbox.sandboxed do
      group = RSpec.describe('sandboxed') { example('one', &body) }
      group.run(RSpec::Core::NullReporter)
      result = group.examples.first.execution_result
    end
    result
  end

  it 'ends the example SKIPPED, not passed, where swiftc cannot import SwiftUI' do
    with_compiler(available: true, swiftui: false) do
      result = run_example { expect('struct A {}').to compile_as_swift }
      expect(result.status).to eq(:pending)
      expect(result.pending_message).to match(/cannot import SwiftUI/)
    end
  end

  it 'ends the example SKIPPED, not passed, where there is no swiftc at all' do
    with_compiler(available: false, swiftui: nil) do
      result = run_example { expect('struct A {}').to compile_as_swift }
      expect(result.status).to eq(:pending)
      expect(result.pending_message).to match(/not on PATH/)
    end
  end

  it 'control: a bare raise of SkipDeclaredInExample ends PASSED, which is why the matcher records first' do
    result = run_example { raise RSpec::Core::Pending::SkipDeclaredInExample, 'unrecorded' }
    expect(result.status).to eq(:passed)
  end

  it 'answers a direct call with a failure, not a pass, when it cannot run' do
    with_compiler(available: false, swiftui: nil) do
      result = SwiftCompiler.compile_check('struct A {}')
      expect(result.success?).to be false
      expect(result.errors).to eq(['swiftc is not on PATH'])
    end
  end

  it 'compiles where the SDK is present' do
    reason = SwiftCompiler.unavailable_reason
    skip reason if reason
    expect('struct A: View { var body: some View { Text("") } }').to compile_as_swift
    expect('struct A: View { var body: some View { Missing() } }').not_to compile_as_swift
  end
end
