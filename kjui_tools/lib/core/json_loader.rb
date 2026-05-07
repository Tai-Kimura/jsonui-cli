#!/usr/bin/env ruby

require 'json'

class JsonLoader
  def initialize(config)
    @config = config
  end

  def load_layout(layout_name)
    layout_file = find_layout_file(layout_name)
    
    if layout_file && File.exist?(layout_file)
      File.read(layout_file)
    else
      nil
    end
  end

  def load_json(file_path)
    if File.exist?(file_path)
      File.read(file_path)
    else
      nil
    end
  end

  private

  def find_layout_file(layout_name)
    # Remove .json extension if present
    layout_name = layout_name.sub(/\.json$/, '')
    
    project_path = @config['project_path'] || Dir.pwd
    
    # Check multiple possible locations
    possible_paths = [
      File.join(project_path, 'src', 'main', 'assets', 'Layouts', "#{layout_name}.json"),
      File.join(project_path, 'app', 'src', 'main', 'assets', 'Layouts', "#{layout_name}.json"),
      File.join(project_path, 'Layouts', "#{layout_name}.json"),
      File.join(project_path, "#{layout_name}.json")
    ]
    
    possible_paths.find { |path| File.exist?(path) }
  end
end