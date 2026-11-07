# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/react_generator'

# A binding is truthy in Ruby, so a bound secure hid the text whatever the data said.
RSpec.describe 'rjui TextField: a bound secure follows the data' do
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }) }

  def emit(attrs)
    generator.send(:convert_component, { 'type' => 'TextField', 'id' => 't' }.merge(attrs), 2).to_s
  end

  it 'chooses the type from the data' do
    expect(emit('secure' => '@{v}')).to include("type={(data.v) ? 'password' : 'text'}")
  end

  it 'falls to the declared input when the data says no' do
    expect(emit('secure' => '@{v}', 'input' => 'email')).to include("type={(data.v) ? 'password' : 'email'}")
  end

  it 'keeps a written secure as it was' do
    expect(emit('secure' => true)).to include('type="password"')
    expect(emit('secure' => false)).to include('type="text"')
    expect(emit({})).to include('type="text"')
    expect(emit('input' => 'password')).to include('type="password"')
  end

  it 'writes what compiles', :typescript_compile do
    drawn = emit('secure' => '@{v}').gsub(/ ref=\{\w+\}/, '').gsub(/ on\w+=\{[^}]*\}\}?/, '')
    source = "const data = {} as { v?: boolean; [key: string]: any };\nexport const view = (\n#{drawn}\n);\n"
    expect(source).to compile_as_typescript
  end
end
