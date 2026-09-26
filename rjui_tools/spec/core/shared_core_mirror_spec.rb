# frozen_string_literal: true

# Every file of lib/core that shared/core also holds is a mirror of the
# canon, byte for byte — the guard sjui_tools and kjui_tools carry with a
# list; here the list is what the two directories share, so a copy added
# later is held too.
RSpec.describe 'shared/core mirrors (rjui)' do
  shared_dir = File.expand_path('../../../shared/core', __dir__)
  copies = Dir[File.expand_path('../../lib/core/*.rb', __dir__)].select { |f| File.exist?(File.join(shared_dir, File.basename(f))) }

  it 'finds the mirrors (enum_spelling.rb among them)' do
    skip 'shared/core not present in this layout' unless Dir.exist?(shared_dir)
    expect(copies.map { |f| File.basename(f) }).to include('enum_spelling.rb', 'attribute_validator_core.rb')
  end

  copies.each do |copy|
    it "keeps lib/core/#{File.basename(copy)} byte-identical to shared/core" do
      expect(File.read(copy)).to eq(File.read(File.join(shared_dir, File.basename(copy))))
    end
  end
end
