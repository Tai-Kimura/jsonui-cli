# frozen_string_literal: true

require 'open3'
require 'rbconfig'

# The process-state guard (spec/support/process_state_guard.rb) looks at the
# state the tool keeps per thread, not only in its modules. A build sets
# ResourceResolver.data_definitions in Thread.current; a spec that built a
# layout declaring `v` with a default left it there, and the next file's
# bound shadow radius read `v` as declared: `data.v.dp` where
# `(data.v?.dp ?: 0.dp)` is written for an undeclared name. It failed on
# seed 41884 only, in the victim (a_bound_number_reaches_kotlin_as_an_
# expression_spec.rb), and the guard did not see it.
RSpec.describe 'the process-state guard reads the state kept per thread' do
  after { Thread.current[:kjui_guard_probe] = nil }

  it 'names a kjui key a group leaves set' do
    before_state = ProcessStateGuard.snapshot
    Thread.current[:kjui_guard_probe] = { 'v' => { 'defaultValue' => 1 } }
    found = ProcessStateGuard.changes(before_state, ProcessStateGuard.snapshot)
    expect(found.map(&:first)).to eq(['Thread.current[:kjui_guard_probe]'])
  end

  it 'reads an emptied key as unset, as every reader does (`|| {}`)' do
    before_state = ProcessStateGuard.snapshot
    Thread.current[:kjui_guard_probe] = {}
    expect(ProcessStateGuard.changes(before_state, ProcessStateGuard.snapshot)).to eq([])
  end

  it 'lists every key the tool keeps per thread as reset by spec_helper' do
    lib = File.expand_path('../../lib', __dir__)
    used = Dir[File.join(lib, '**', '*.rb')].flat_map { |f| File.read(f).scan(/Thread\.current\[:(kjui_\w+)\]/).flatten }.uniq
    expect(used).not_to be_empty
    expect(used.map { |k| "Thread.current[:#{k}]" } - ProcessStateGuard::MANAGED.keys).to eq([])
  end

  # The order of seed 41884, cut to the two files: a build that declares `v`
  # with a default, then the shadow example that reads `v` as undeclared.
  it 'starts the next file without the data a build declared' do
    tool = File.expand_path('../..', __dir__)
    cmd = [RbConfig.ruby, '-S', 'rspec', '--order', 'defined',
           'spec/compose/a_bound_value_slot_reaches_the_code_spec.rb',
           'spec/compose/a_bound_number_reaches_kotlin_as_an_expression_spec.rb:65']
    env = { 'PROCESS_STATE_GUARD_REPORT' => nil, 'KJUI_REQUIRE_KOTLINC' => nil }
    out, status = Open3.capture2e(env, *cmd, chdir: tool)
    summary = out[/\d+ examples?, \d+ failures?/]
    expect(summary).to match(/\A\d+ examples, 0 failures\z/), out.lines.last(30).join
    expect(status).to be_success
  end
end
