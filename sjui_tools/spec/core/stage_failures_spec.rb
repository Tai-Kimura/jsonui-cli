# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'core/stage_failures'

# The ledger (shared/core/stage_failures.rb, mirrored into the three tools).
# Ticket uikit-build-reports-success-after-a-binding-error.
RSpec.describe JsonUI::StageFailures do
  let(:said) { [] }
  let(:logger) do
    lines = said
    Object.new.tap do |l|
      l.define_singleton_method(:error) { |m| lines << [:error, m] }
      l.define_singleton_method(:success) { |m| lines << [:success, m] }
    end
  end

  before { described_class.clear! }
  after { described_class.clear! }

  it 'records a failure met on every visit once, and two different ones twice' do
    3.times { described_class.record_once('config', 'a.json could not be parsed') }
    described_class.record_once('config', 'b.json could not be parsed')
    described_class.record_once('styles', 'a.json could not be parsed')
    expect(described_class.entries.map { |e| [e[:stage], e[:message][0]] }).to eq([%w[config a], %w[config b], %w[styles a]])
  end

  it 'closes on the success line only when nothing failed' do
    described_class.conclude(logger, 'Build completed!')
    described_class.record('layout', 'x.json was not generated')
    described_class.conclude(logger, 'Build completed!')
    expect(said).to eq([[:success, 'Build completed!'],
                        [:error, 'Build finished with 1 stage(s) incomplete — see above']])
  end

  # `sjui build --mode all` reports after the UIKit stage and again after the
  # SwiftUI one; until 1.8.121 the second report wrote the first one's
  # entries into the ledger again.
  it 'writes each entry into the ledger once, however many times the build reports' do
    Dir.mktmpdir('ledger') do |dir|
      path = File.join(dir, 'ledger.json')
      saved = ENV['JUI_STAGE_FAILURES']
      ENV['JUI_STAGE_FAILURES'] = path
      begin
        described_class.record('colors', 'one')
        described_class.report!(logger)
        described_class.report!(logger)
        described_class.record('layout', 'two')
        described_class.report!(logger)
        expect(JSON.parse(File.read(path)).map { |e| e['message'] }).to eq(%w[one two])

        # A cleared ledger starts over: what it records next is written.
        described_class.clear!
        described_class.record('layout', 'three')
        described_class.report!(logger)
        expect(JSON.parse(File.read(path)).map { |e| e['message'] }).to eq(%w[one two three])
      ensure
        ENV['JUI_STAGE_FAILURES'] = saved
      end
    end
  end
end
