# frozen_string_literal: true

require_relative '../spec_helper'
require 'core/generated_marker'

RSpec.describe RjuiTools::Core::GeneratedMarker do
  describe '.comment_header' do
    # Regression: rjui-generated-code-eslint-violations — generated TS/JS is
    # machine-owned and regenerated every build, so consumer lint configs
    # must not gate on it. The banner carries a blanket eslint-disable.
    it 'prepends a blanket eslint-disable for TS/JS output' do
      header = described_class.comment_header(source: 'XData', generator: 'rjui build')
      expect(header).to start_with("/* eslint-disable */\n")
      expect(header).to include('@generated AUTO-GENERATED FILE')
    end

    it 'keeps non-JS prefixes free of eslint pragmas' do
      header = described_class.comment_header(source: 'X', generator: 'rjui build', prefix: '#')
      expect(header).not_to include('eslint-disable')
      expect(header).to include('# ║  @generated AUTO-GENERATED FILE')
    end
  end
end
