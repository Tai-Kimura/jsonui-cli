#!/usr/bin/env ruby

module XmlGenerator
  class BindingParser
    def initialize
      @bindings = []
    end

    def parse(value)
      # Convert @{variable} syntax to Android data binding
      if value.start_with?('@{') && value.end_with?('}')
        # Extract the binding expression
        expression = value[2..-2]
        
        # Track the binding
        @bindings << expression
        
        # Return Android data binding format
        "@{#{convert_expression(expression)}}"
      else
        value
      end
    end

    def get_bindings
      @bindings.uniq
    end

    def has_bindings?
      !@bindings.empty?
    end

    private

    def convert_expression(expression)
      # Handle different binding patterns
      
      # Simple variable binding: @{userName} -> @{data.userName}
      if expression.match?(/^\w+$/)
        return "data.#{expression}"
      end
      
      # Property access: @{user.name} -> @{data.user.name}
      if expression.match?(/^[\w.]+$/)
        return "data.#{expression}"
      end
      
      # Method call: @{getUserName()} -> @{viewModel.getUserName()}
      if expression.include?('(')
        if expression.start_with?('viewModel.')
          return expression
        else
          return "viewModel.#{expression}"
        end
      end
      
      # Conditional expression: @{isVisible ? View.VISIBLE : View.GONE}
      if expression.include?('?')
        return process_conditional(expression)
      end
      
      # String concatenation: @{`Hello ${userName}`}
      if expression.include?('${')
        return process_string_template(expression)
      end
      
      # Default: return as is
      expression
    end

    def process_conditional(expression)
      # Convert conditional expressions
      parts = expression.split(/\s*\?\s*/)
      if parts.length == 2
        condition = parts[0]
        values = parts[1].split(/\s*:\s*/)
        
        if values.length == 2
          # Add data. prefix to condition if it's a simple variable
          if condition.match?(/^\w+$/)
            condition = "data.#{condition}"
          end
          
          # Process visibility values
          true_value = process_value(values[0])
          false_value = process_value(values[1])
          
          return "#{condition} ? #{true_value} : #{false_value}"
        end
      end
      
      expression
    end

    def process_string_template(expression)
      # Convert string template: `Hello ${userName}` -> @{`Hello ` + data.userName}
      if expression.start_with?('`') && expression.end_with?('`')
        template = expression[1..-2]
        
        # Replace ${variable} with ` + data.variable + `
        template.gsub!(/\$\{(\w+)\}/) do |match|
          "` + data.#{$1} + `"
        end
        
        "`#{template}`"
      else
        expression
      end
    end

    def process_value(value)
      # Process special values
      case value.strip
      when 'true', 'false'
        value
      when 'VISIBLE', 'View.VISIBLE'
        'View.VISIBLE'
      when 'INVISIBLE', 'View.INVISIBLE'
        'View.INVISIBLE'
      when 'GONE', 'View.GONE'
        'View.GONE'
      else
        # Check if it's a simple variable
        if value.match?(/^\w+$/)
          "data.#{value}"
        else
          value
        end
      end
    end
  end

  class DataBindingManager
    def initialize
      @variables = Set.new
      @imports = Set.new
      @converters = []
    end

    def add_variable(name, type = 'String')
      @variables.add({ name: name, type: type })
    end

    def add_import(class_name)
      @imports.add(class_name)
    end

    def add_converter(converter)
      @converters << converter
    end

    def generate_data_binding_layout(xml_content)
      # Wrap the layout in <layout> tags for data binding
      doc = Nokogiri::XML(xml_content)
      
      # Create new document with layout root
      builder = Nokogiri::XML::Builder.new(encoding: 'UTF-8') do |xml|
        xml.layout('xmlns:android' => 'http://schemas.android.com/apk/res/android',
                  'xmlns:app' => 'http://schemas.android.com/apk/res-auto',
                  'xmlns:tools' => 'http://schemas.android.com/tools') do
          
          # Add data section
          xml.data do
            # Add imports
            @imports.each do |import|
              xml.import(type: import)
            end
            
            # Add variables
            @variables.each do |var|
              xml.variable(name: var[:name], type: var[:type])
            end
            
            # Add ViewModel variable
            xml.variable(name: 'viewModel', type: "com.example.viewmodel.#{get_view_model_name}")
          end
          
          # Add the original layout content (without XML declaration)
          xml << doc.root.to_xml
        end
      end
      
      builder.to_xml(indent: 4)
    end

    private

    def get_view_model_name
      # Generate ViewModel class name from layout name
      # This should be passed in or configured
      'MainViewModel'
    end
  end
end