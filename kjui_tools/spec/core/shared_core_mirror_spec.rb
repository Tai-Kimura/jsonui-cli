# frozen_string_literal: true

# responsive_resolver.rb and layout_validator.rb are maintained in
# shared/core/ and mirrored into each tool's lib/core/. A drifted mirror
# silently forks behavior per toolchain, so each copy is pinned
# byte-for-byte to the canon — the same guard plural_validator and
# screen_index already carry.
RSpec.describe 'shared/core mirrors' do
  %w[responsive_resolver.rb layout_validator.rb attribute_validator_core.rb data_model_updater_core.rb converter_generator_core.rb].each do |file|
    it "keeps lib/core/#{file} byte-identical to the canonical shared/core copy" do
      tool_copy = File.expand_path("../../lib/core/#{file}", __dir__)
      shared_copy = File.expand_path("../../../shared/core/#{file}", __dir__)
      skip 'shared/core copy not present in this layout' unless File.exist?(shared_copy)
      expect(File.read(tool_copy)).to eq(File.read(shared_copy))
    end
  end
end
