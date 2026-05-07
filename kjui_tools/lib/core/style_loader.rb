#!/usr/bin/env ruby

require 'json'

class StyleLoader
  def initialize(config)
    @config = config
    @styles = {}
    load_styles
  end

  def apply_styles(json_data)
    apply_styles_recursive(json_data)
    json_data
  end

  private

  def load_styles
    project_path = @config['project_path'] || Dir.pwd
    styles_dir = File.join(project_path, 'src', 'main', 'assets', 'Styles')
    styles_dir = File.join(project_path, 'app', 'src', 'main', 'assets', 'Styles') unless Dir.exist?(styles_dir)
    return unless Dir.exist?(styles_dir)

    Dir.glob(File.join(styles_dir, '*.json')).each do |style_file|
      style_name = File.basename(style_file, '.json')
      begin
        style_content = File.read(style_file)
        @styles[style_name] = JSON.parse(style_content)
      rescue => e
        puts "Warning: Failed to load style #{style_name}: #{e.message}"
      end
    end
  end

  def apply_styles_recursive(element)
    return unless element.is_a?(Hash)

    # Apply style if present
    if element['style']
      style_names = element['style'].is_a?(Array) ? element['style'] : [element['style']]
      
      style_names.each do |style_name|
        if @styles[style_name]
          # Merge style attributes (style attributes are overridden by inline attributes)
          @styles[style_name].each do |key, value|
            element[key] = value unless element.key?(key)
          end
        end
      end
      
      # Remove style attribute after applying
      element.delete('style')
    end

    # Apply recursively to children
    if element['children']
      element['children'].each { |child| apply_styles_recursive(child) }
    elsif element['child']
      if element['child'].is_a?(Array)
        element['child'].each { |child| apply_styles_recursive(child) }
      else
        apply_styles_recursive(element['child'])
      end
    end
  end
end