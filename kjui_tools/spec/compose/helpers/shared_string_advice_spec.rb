# frozen_string_literal: true

require 'compose/helpers/resource_resolver'
require 'tmpdir'

# Reported 2026-09-07: two warnings whose repairs regenerated each other.
# "Register it under your own section" creates a second declaration, which
# is the duplicate warning; deleting the duplicate brings this one back. A
# user following the tool cycled 1 -> 2 -> 1 and never reached zero, so a
# project whose invariant is `jui build` warning 0 could not share a string
# between layouts at all.
#
# The key-qualified spelling was already the supported way out — the lookup
# comments say a section-qualified hit is "a deliberate reference" — so what
# was missing was only the sentence that names it.
RSpec.describe KjuiTools::Compose::Helpers::ResourceResolver, 'shared-string advice' do
  let(:resolver) { described_class }
  let(:strings) { { 'intro' => { 'product_name' => 'Acme' } } }
  let(:tmp) { Dir.mktmpdir }

  before do
    allow(resolver).to receive(:cached_strings_data).and_return(strings)
    allow(KjuiTools::Core::Logger).to receive(:warn)
    resolver.current_namespaces = %w[messages]
  end

  after { FileUtils.rm_rf(tmp) }

  def resolve(text)
    resolver.send(:find_string_key, text, {}, tmp)
  end

  it 'names the key form, which is the spelling that reaches zero' do
    resolve('Acme')
    expect(KjuiTools::Core::Logger).to have_received(:warn).with(
      satisfy do |m|
        # ONE matcher, not two: `.with(a).with(b)` keeps only the LAST,
        # so the chained form asserted the second pattern and silently
        # dropped the first. Removing "name the KEY instead of the value"
        # from both faces left this arm green (measured 2026-09-07).
        m =~ /name the KEY instead of the value/ &&
          m =~ /"defaultValue": "<section>_<key>"/
      end
    )
  end

  it 'says why the obvious repair loops' do
    resolve('Acme')
    expect(KjuiTools::Core::Logger).to have_received(:warn)
      .with(/regenerate each other/)
  end

  it 'is silent for the spelling it recommends' do
    expect(resolve('intro_product_name')).to eq('intro_product_name')
    expect(KjuiTools::Core::Logger).not_to have_received(:warn)
  end

  it 'still reports a BARE foreign key, which is a different finding' do
    # The qualified form must not be waved through by disabling this gate:
    # a bare key hitting a foreign section is a collision, not a reference.
    expect(resolve('product_name')).to be_nil
    expect(KjuiTools::Core::Logger).to have_received(:warn)
      .with(/Bare key "product_name" is declared only in foreign/)
  end

  it 'carries the same advice as the iOS face, word for word' do
    # Two tools giving different advice for one situation is the shape the
    # report is about. Pinned across the faces rather than once per face,
    # because a one-sided edit is exactly what this must catch.
    def message(path, marker)
      src = File.read(path, encoding: 'UTF-8')
      src[/#{Regexp.escape(marker)}.*?jsonui-localize\)\./m]
         .gsub(/"\s*\\\n\s*"/, '').gsub(/\s+/, ' ')
    end

    root = File.expand_path('../../../..', __dir__)
    ios = message(File.join(root, 'sjui_tools/lib/swiftui/helpers/string_manager_helper.rb'),
                  'To share one string')
    android = message(File.join(root, 'kjui_tools/lib/compose/helpers/resource_resolver.rb'),
                      'To share one string')
    expect(android).to eq(ios)
  end
end
