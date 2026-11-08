# frozen_string_literal: true

require 'compose/helpers/resource_resolver'

# A `_` key in colors.json is a note, not a colour (ColorManagerCore.note_key?).
# find_color_key answered a top-level `_comment` as a colors.json key, so a
# Layout naming it got ColorManager.compose.color("_comment") — a colour the
# generated ColorManager no longer has since 2.5.14.
RSpec.describe KjuiTools::Compose::Helpers::ResourceResolver do
  def key_for(color, colors)
    allow(described_class).to receive(:cached_colors_data).and_return(colors)
    described_class.send(:find_color_key, color, { 'source_directory' => 'src/main' }, Dir.tmpdir)
  end

  it 'does not answer a note as a colour key' do
    expect(key_for('_comment', { '_comment' => 'n', 'ink' => '#111111' })).to be_nil
  end

  it 'control: a colour key is still a key' do
    expect(key_for('ink', { '_comment' => 'n', 'ink' => '#111111' })).to eq('ink')
  end
end
