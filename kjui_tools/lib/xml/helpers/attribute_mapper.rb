#!/usr/bin/env ruby

require 'json'
require_relative 'mappers/dimension_mapper'
require_relative 'mappers/text_mapper'
require_relative 'mappers/layout_mapper'
require_relative 'mappers/style_mapper'
require_relative 'mappers/input_mapper'

module XmlGenerator
  class AttributeMapper
    def initialize(drawable_generator = nil, string_resource_manager = nil)
      @dimension_mapper = Mappers::DimensionMapper.new
      @text_mapper = Mappers::TextMapper.new(string_resource_manager)
      @layout_mapper = Mappers::LayoutMapper.new(@dimension_mapper)
      @style_mapper = Mappers::StyleMapper.new(@text_mapper, drawable_generator)
      @input_mapper = Mappers::InputMapper.new
      @drawable_generator = drawable_generator
      @string_resource_manager = string_resource_manager
      
      @attribute_map = create_attribute_map
    end
    
    def map_dimension(value)
      @dimension_mapper.map_dimension(value)
    end
    
    def map_attribute(key, value, component_type, parent_type = nil, json_element = nil)
      # Skip problematic data binding expressions for specific attributes
      if should_skip_binding?(key, value, component_type)
        log_skipped_binding(key, value, component_type)
        puts "Skipping binding: #{key}=#{value} for #{component_type}" if ENV['DEBUG']
        return nil
      end
      
      # Try layout attributes first (includes dimensions, padding, margin, alignment)
      result = @layout_mapper.map_layout_attributes(key, value, component_type, parent_type)
      return result if result
      
      # Try alignment attributes
      result = @layout_mapper.map_alignment_attributes(key, value, parent_type)
      return result if result
      
      # Try text attributes
      result = @text_mapper.map_text_attributes(key, value, component_type)
      return result if result
      
      # Try style attributes (with json_element for drawable generation)
      result = @style_mapper.map_style_attributes(key, value, json_element, component_type)
      return result if result
      
      # Try input attributes
      result = @input_mapper.map_input_attributes(key, value)
      return result if result
      
      # Custom component properties (store as tag or tools attribute)
      case key
      when 'title'
        # Don't use tools: namespace for data binding expressions
        if value.to_s.start_with?('@{')
          return nil  # Skip tools attributes with data binding
        end
        return { namespace: 'tools', name: 'title', value: value }
      when 'count'
        # Don't use tools: namespace for data binding expressions
        if value.to_s.start_with?('@{')
          return nil  # Skip tools attributes with data binding
        end
        return { namespace: 'tools', name: 'count', value: value.to_s }
      when /^constraint/
        return map_constraint_attribute(key, value)
      else
        # Check if it's in the standard map
        if @attribute_map[key]
          mapped = @attribute_map[key]
          return { 
            namespace: mapped[:namespace] || 'android', 
            name: mapped[:name], 
            value: convert_value(value, mapped[:type])
          }
        end
      end
      
      nil
    end
    
    private
    
    def should_skip_binding?(key, value, component_type)
      return false unless value.to_s.include?('@{')
      
      # List of problematic bindings that need to be skipped
      problematic_bindings = [
        # RecyclerView items binding - Skip this as it needs complex adapter implementation
        { key: 'items', component: 'RecyclerView' },
        { key: 'items', component: 'Collection' },
        # StatusColor binding - Compose UI Color type not supported in data binding
        { key: 'tint', value_contains: 'statusColor' },
        { key: 'color', value_contains: 'statusColor' },  # color is sometimes mapped to tint
        # Visibility binding - String type not supported
        { key: 'visibility', value_contains: '@{' },
        # Progress binding - double type not supported
        { key: 'progress', value_contains: '@{' },
        # Slider value binding (maps to progress) - double type not supported
        { key: 'value', component: 'Slider', value_contains: '@{' }
      ]
      
      problematic_bindings.any? do |binding|
        if binding[:component]
          key == binding[:key] && component_type&.include?(binding[:component])
        elsif binding[:value_contains]
          key == binding[:key] && value.to_s.include?(binding[:value_contains])
        elsif binding[:type]
          key == binding[:key] && value.to_s.include?('.')  # Assumes object property access
        else
          key == binding[:key]
        end
      end
    end
    
    def log_skipped_binding(key, value, component_type)
      @skipped_bindings ||= []
      @skipped_bindings << {
        attribute: key,
        value: value,
        component: component_type,
        reason: 'Requires custom binding adapter'
      }
      
      # Write to a file that can be accessed later
      File.open('/tmp/skipped_bindings.json', 'w') do |f|
        f.write(@skipped_bindings.to_json)
      end
    end
    
    def create_attribute_map
      {
        # Additional mappings not covered by specific mappers
        'contentDescription' => { name: 'contentDescription', type: 'string' },
        'tag' => { name: 'tag', type: 'string' },
        'transitionName' => { name: 'transitionName', type: 'string' },
        'elevation' => { name: 'elevation', type: 'dimension' },
        'translationZ' => { name: 'translationZ', type: 'dimension' },
        'rotation' => { name: 'rotation', type: 'float' },
        'rotationX' => { name: 'rotationX', type: 'float' },
        'rotationY' => { name: 'rotationY', type: 'float' },
        'scaleX' => { name: 'scaleX', type: 'float' },
        'scaleY' => { name: 'scaleY', type: 'float' }
      }
    end
    
    def convert_value(value, type)
      case type
      when 'dimension'
        @dimension_mapper.convert_dimension(value)
      when 'float'
        value.to_f.to_s
      when 'integer'
        value.to_i.to_s
      when 'boolean'
        value.to_s
      else
        value
      end
    end
    
    def map_constraint_attribute(key, value)
      # ConstraintLayout attributes mapping
      constraint_map = {
        'constraintStartToStartOf' => 'layout_constraintStart_toStartOf',
        'constraintEndToEndOf' => 'layout_constraintEnd_toEndOf',
        'constraintTopToTopOf' => 'layout_constraintTop_toTopOf',
        'constraintBottomToBottomOf' => 'layout_constraintBottom_toBottomOf',
        'constraintStartToEndOf' => 'layout_constraintStart_toEndOf',
        'constraintEndToStartOf' => 'layout_constraintEnd_toStartOf',
        'constraintTopToBottomOf' => 'layout_constraintTop_toBottomOf',
        'constraintBottomToTopOf' => 'layout_constraintBottom_toTopOf'
      }
      
      if constraint_map[key]
        constraint_value = value == 'parent' ? 'parent' : "@id/#{value}"
        return { namespace: 'app', name: constraint_map[key], value: constraint_value }
      end
      
      nil
    end
  end
end