#!/usr/bin/env ruby

module XmlGenerator
  module Mappers
    class DimensionMapper
      def map_dimension(value)
        # Handle nil or empty string
        return 'wrap_content' if value.nil? || value.to_s.empty?
        
        case value
        when 'matchParent', 'match_parent'
          'match_parent'
        when 'wrapContent', 'wrap_content'
          'wrap_content'
        when Integer, Float
          "#{value.to_i}dp"
        when /^\d+$/
          "#{value}dp"
        when /^\d+\.\d+$/
          "#{value.to_f.to_i}dp"
        when /^\d+dp$/
          value
        when /^\d+%$/
          "0dp" # Will need layout_weight
        else
          value.to_s.empty? ? 'wrap_content' : value.to_s
        end
      end
      
      def convert_dimension(value)
        case value
        when Integer, Float
          "#{value.to_i}dp"
        when String
          if value.match?(/^\d+$/)
            "#{value}dp"
          else
            value
          end
        when Array
          # Use first value for now
          convert_dimension(value.first || 0)
        else
          value.to_s
        end
      end
    end
  end
end