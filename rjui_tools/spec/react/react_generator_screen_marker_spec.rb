# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

# Screen marker emission (screen-identity track, Phase 4).
#
# Web is the one platform whose STATIC output the conformance suite renders,
# but the suite has no screen concept — so the generated string is the
# regression test here too.
RSpec.describe RjuiTools::React::ReactGenerator do
  let(:config) { { 'typescript' => true } }
  let(:generator) { described_class.new(config) }

  let(:layout) do
    {
      'type' => 'View',
      'id' => 'root_view',
      'child' => [{ 'type' => 'Label', 'id' => 'title', 'text' => 'hello' }]
    }
  end

  describe 'screen marker' do
    it 'puts data-screen on the root element, gated on NODE_ENV' do
      output = generator.generate('Home', layout, screen_id: 'home')

      expect(output).to include(%({...screenMarker("home")}))
      expect(output).to include("import { screenMarker } from '@/generated/screenMarker';")
    end


    it 'passes the BARE screen id — the runtime layer owns the __screen_ prefix' do
      # Regression: codegen used to pass the already-prefixed marker while
      # the library prefixed again, producing __screen___screen_<id> on a
      # real device.
      expect(generator.generate('Home', layout, screen_id: 'home'))
        .not_to include('"__screen_')
    end

    it 'marks the SAME element that carries the root id' do
      output = generator.generate('Home', layout, screen_id: 'home')
      root_tag = output[/return \(\s*(<[^>]*>)/m, 1]

      # A separate node would need its own non-empty box to satisfy the
      # driver's visibility predicate; riding the root means the marker is
      # visible exactly when the screen is.
      expect(root_tag).to include('screenMarker("home")')
      expect(root_tag).to include('id={id')
    end

    it 'emits nothing for a non-screen layout' do
      output = generator.generate('ItemCell', layout)
      expect(output).not_to include('screenMarker')
      expect(output).not_to include('data-screen')
    end

    it 'leaves unmarked output byte-identical to the pre-marker generator' do
      expect(generator.generate('Home', layout, screen_id: nil))
        .to eq(described_class.new(config).generate('Home', layout))
    end

    it 'is deterministic — generating twice produces the same output' do
      first = generator.generate('Home', layout, screen_id: 'home')
      expect(described_class.new(config).generate('Home', layout, screen_id: 'home'))
        .to eq(first)
    end

    it 'skips an expression-container root, like id injection does' do
      hidden = layout.merge('visibility' => '@{isVisible}')
      output = generator.generate('Home', hidden, screen_id: 'home')

      # No crash, and nothing injected into a fragment.
      expect(output).not_to include('<> {...screenMarker')
    end
  end
end
