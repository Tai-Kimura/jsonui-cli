# frozen_string_literal: true

require 'spec_helper'
require 'tmpdir'
require 'fileutils'
require_relative '../../lib/compose/converter_test_tag_audit'

# v1.8.56 fixed the converter TEMPLATE to emit a testTag. That fix reaches
# converters generated afterwards and no others, and nothing counted the
# others: one face had 0 of 8 hand-written converters emitting it while the
# built-ins were at 27 of 28.
RSpec.describe KjuiTools::Compose::ConverterTestTagAudit do
  def face(with:, without:)
    dir = Dir.mktmpdir
    FileUtils.mkdir_p(File.join(dir, 'components', 'extensions'))
    # A built-in that has it, so the reported denominator is not zero.
    File.write(File.join(dir, 'components', 'builtin_component.rb'),
               "Helpers::ModifierBuilder.build_test_tag(json_data)\n")
    with.each do |n|
      File.write(File.join(dir, 'components', 'extensions', "#{n}_component.rb"),
                 "Helpers::ModifierBuilder.build_test_tag(json_data)\n")
    end
    without.each do |n|
      File.write(File.join(dir, 'components', 'extensions', "#{n}_component.rb"),
                 "def generate(json_data, depth, imports); end\n")
    end
    dir
  end

  it 'names each converter that does not emit a testTag' do
    dir = face(with: %w[modern], without: %w[legacy older])
    lines = described_class.findings(dir)
    expect(lines.length).to eq(1)
    expect(lines.first).to include('2 of 3 converter(s)')
    expect(lines.first).to include('legacy_component.rb')
    expect(lines.first).to include('older_component.rb')
  ensure
    FileUtils.remove_entry(dir)
  end

  it 'prints the built-in ratio beside it' do
    # ⚠️ 0/8 alone reads as a convention. Beside a population that almost all
    # has it, the same number is a gap. Both are reported, always.
    dir = face(with: [], without: %w[legacy])
    expect(described_class.findings(dir).first).to include('Built-in components: 1/1')
  ensure
    FileUtils.remove_entry(dir)
  end

  it 'the control: says nothing when every converter emits it' do
    dir = face(with: %w[a b], without: [])
    expect(described_class.findings(dir)).to eq([])
  ensure
    FileUtils.remove_entry(dir)
  end

  it 'the control: says nothing when there are no converters at all' do
    # A project that never ran `jui g converter` has nothing to be missing.
    # A line that fired on the absence of an optional directory would print
    # for most projects, which is how a warning teaches people to stop reading.
    dir = face(with: [], without: [])
    expect(described_class.findings(dir)).to eq([])
  ensure
    FileUtils.remove_entry(dir)
  end

  it 'matches the real built-in population, so the denominator is not invented' do
    base = File.expand_path('../../lib/compose', __dir__)
    missing, total = described_class.scan(described_class.builtins_dir(base))
    expect(total).to be > 20
    expect(total - missing.length).to be >= total - 1
  end
end

# 🚨 Added for the same reason the jui-build counterpart needed one: every
# example above drives the audit directly, so they say it computes the right
# answer — not that `kjui build` ever runs it. A check nobody calls prints
# nothing, and "nobody called it" is precisely the defect being fixed.
RSpec.describe 'the audit is wired into the build' do
  let(:build_rb) do
    File.read(File.expand_path('../../lib/cli/commands/build.rb', __dir__))
  end

  it 'build_compose calls the audit' do
    expect(build_rb).to include('ConverterTestTagAudit.findings')
  end

  it 'the call sits inside build_compose, before the builder runs' do
    # 🚨 Matches on `ConverterTestTagAudit.findings`, NOT the bare class name.
    # The bare name also appears in the comment ABOVE the call ("see
    # ConverterTestTagAudit for why both numbers print"), and a comment does
    # not move when the call does. Measured 2026-09-08 by the triage lane:
    # with the bare spelling this arm scored the comment at offset 265 while
    # the call was at 402, so moving the call BELOW ComposeBuilder.new left it
    # green. `.findings` is unambiguous because the comment does not contain it.
    #
    # ⚠️ Same family as the defect v1.8.56 fixed — a comment being counted as
    # the thing it describes — shipped again in v1.8.57 in this very file.
    body = build_rb[/def build_compose\b.*?\n(?=        def |\n        # ---)/m] ||
           build_rb[/def build_compose.*?\n        end/m]
    expect(body).to include('ConverterTestTagAudit.findings')
    expect(body.index('ConverterTestTagAudit.findings')).to be < body.index('ComposeBuilder.new')
  end
end
