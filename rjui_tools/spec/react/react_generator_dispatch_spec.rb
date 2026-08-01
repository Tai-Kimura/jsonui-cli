# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

# Root-level dispatch for the five converters that existed (and were
# unit-tested) but were never required by the generator: until 2026-08-01
# these types silently degraded to a plain View at root position while the
# child dispatch map in BaseConverter already knew them. These examples pin
# the wiring end-to-end and the root/child rendering equivalence.
RSpec.describe RjuiTools::React::ReactGenerator do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:generator) { described_class.new(config) }

  def root(json)
    generator.send(:convert_component, json, 2)
  end

  describe 'formerly-orphan converters dispatch at root' do
    it 'IconLabel renders the icon/text flex pair with iconPosition mapped to flex direction' do
      out = root('type' => 'IconLabel', 'id' => 'il', 'text' => 'Star',
                 'icon' => 'star.png', 'iconPosition' => 'Top')
      expect(out).to include('flex flex-col items-center')
      expect(out).to include('<img')
      expect(out).to include('<span')
      expect(out).not_to include('<div id="il" className="" />')
    end

    it 'CircleView renders a rounded-full clipped div with centered content' do
      out = root('type' => 'CircleView', 'id' => 'cv', 'background' => '#FF0000',
                 'child' => [{ 'type' => 'Label', 'text' => 'C' }])
      expect(out).to include('rounded-full overflow-hidden flex items-center justify-center')
    end

    it 'Web renders a sandboxed iframe' do
      out = root('type' => 'Web', 'id' => 'wv', 'url' => 'https://example.com')
      expect(out).to include('<iframe')
      expect(out).to include('sandbox="allow-scripts allow-same-origin allow-forms"')
      expect(out).to include('src="https://example.com"')
    end

    it 'Blur renders a backdrop-filter div' do
      out = root('type' => 'Blur', 'id' => 'bl', 'blurRadius' => 10,
                 'child' => [{ 'type' => 'Label', 'text' => 'B' }])
      expect(out).to include("backdropFilter: 'blur(10px)'")
      expect(out).to include("WebkitBackdropFilter: 'blur(10px)'")
    end

    it 'GradientView renders a CSS gradient background' do
      out = root('type' => 'GradientView', 'id' => 'gv',
                 'colors' => ['#FF0000', '#0000FF'], 'orientation' => 'vertical')
      expect(out).to include("background: 'linear-gradient(to bottom, #FF0000, #0000FF)'")
    end
  end

  describe 'root and child dispatch stay in step' do
    it 'renders a nested Web the same way the root path does' do
      nested = root('type' => 'View', 'child' => [
                      { 'type' => 'Web', 'id' => 'wv', 'url' => 'https://example.com' }
                    ])
      expect(nested).to include('<iframe')
      expect(nested).to include('src="https://example.com"')
    end
  end

  describe 'unknown types are no longer a silent degrade' do
    it 'warns once and still renders the plain-View fallback' do
      out = nil
      expect { out = root('type' => 'Mystery', 'id' => 'm') }
        .to output(/Unknown component type 'Mystery' — rendering as a plain View/).to_stdout
      expect(out).to include('<div id="m"')
    end

    it 'does not warn for the deliberate SafeAreaView → View mapping' do
      expect { root('type' => 'SafeAreaView', 'id' => 's') }
        .not_to output(/Unknown component type/).to_stdout
    end
  end
end
