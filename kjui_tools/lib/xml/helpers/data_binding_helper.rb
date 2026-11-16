#!/usr/bin/env ruby

module XmlGenerator
  class DataBindingHelper
    def self.process_data_binding(value)
      return nil if value.nil?
      # Convert @{variable} to Android data binding format
      if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        # Already in binding format, just ensure proper data. prefix
        expr = value[2..-2]
        
        # Add data. prefix if it's a simple variable
        if expr.match?(/^\w+$/)
          "@{data.#{expr}}"
        elsif expr.include?('(') && !expr.include?('viewModel.')
          # Method call without viewModel prefix
          "@{viewModel.#{expr}}"
        else
          # Keep as is (already has proper prefix or is complex expression)
          value
        end
      else
        value
      end
    end
  end
end