# frozen_string_literal: true

require 'core/string_literals'

# A String defaultValue spelled bare — the canonical spelling, and every one
# the faces write — reads as itself on every path (the ruling behind
# JsonUIShared::StringLiterals.default_text: '' is empty, "…" is read with
# JSON's escapes, '…' is the text between the quotes, bare is the text as
# written). Only a value quoted at BOTH ends is read differently, so a quote
# at one end, or inside, leaves it as written.
#
# Measured 2026-09-26 (jsonui-cli 1.9.0), read only: the three faces' declared
# layout trees hold 1142 String defaults, all bare, and default_text returns
# each one unchanged (3784 counting the platform copies of those trees; the
# same). shared/core/string_literals.rb is byte-identical in the three tools,
# so this one spec holds all three.
RSpec.describe 'a bare String default reads as itself' do
  BARE = [
    'a', '', ' spaced ', 'it\'s', "'a", "a'", '"a', 'a"', "'a' and 'b'x", '"a" and "b"x',
    "'", '"', '\\n', '\\"', '{x}', '@{x}', '#{x}', '$x', '日本語', 'a''b', 'x\'\'', "''x",
    'C:\\new', 'emoji 🍶', "tab\tinside", 'gone'
  ].freeze

  it 'is its text, whatever it holds between its ends' do
    aggregate_failures do
      BARE.each do |spelling|
        expect(JsonUIShared::StringLiterals.default_text(spelling)).to eq(spelling), spelling.inspect
      end
    end
  end

  it 'is told from a quoted one only by a quote at both ends (the control)' do
    expect(JsonUIShared::StringLiterals.default_text("'a'")).to eq('a')
    expect(JsonUIShared::StringLiterals.default_text('"a"')).to eq('a')
    expect(JsonUIShared::StringLiterals.default_text("''")).to eq('')
  end
end
