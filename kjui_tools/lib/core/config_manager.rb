# frozen_string_literal: true

require 'json'
require 'pathname'

module KjuiTools
  module Core
    class ConfigManager
      CONFIG_FILE = 'kjui.config.json'
      
      DEFAULT_CONFIG = {
        'mode' => 'compose',
        'project_name' => '',
        'package_name' => 'com.example.app',
        'source_directory' => 'app/src/main',
        'layouts_directory' => 'assets/Layouts',
        'styles_directory' => 'assets/Styles',
        'view_directory' => 'kotlin/com/example/app/views',
        'data_directory' => 'kotlin/com/example/app/data',
        'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
        'extension_directory' => 'library/src/main/kotlin/com/kotlinjsonui/extensions',
        'adapter_directory' => 'library/src/main/kotlin/com/kotlinjsonui/adapters',
        'custom_view_types' => {},
        'compose' => {
          'output_directory' => 'kotlin/com/example/app/generated'
        },
        'xml' => {
          'bindings_directory' => 'java/com/example/app/bindings'
        }
      }.freeze
      
      class << self
        def load_config
          config_path = find_config_file
          
          base_config = if config_path && File.exist?(config_path)
            begin
              config_data = JSON.parse(File.read(config_path))
              # Store the config directory for use by generators
              config_data['_config_dir'] = File.dirname(config_path)
              config_data
            rescue JSON::ParserError => e
              puts "Error parsing config file: #{e.message}"
              {}
            end
          else
            {}
          end
          
          # Merge with default config to ensure all keys exist
          deep_merge(DEFAULT_CONFIG, base_config)
        end
        
        # Find config file in project
        def find_config_file
          # First check current directory
          return CONFIG_FILE if File.exist?(CONFIG_FILE)
          
          # Check subdirectories for kjui.config.json
          Dir.glob(File.join(Dir.pwd, '**/kjui.config.json')).each do |config_path|
            # Skip hidden directories and node_modules
            next if config_path.include?('/.') || config_path.include?('/node_modules/')
            return config_path
          end
          
          # Check parent directories up to 3 levels
          current = Dir.pwd
          3.times do
            current = File.dirname(current)
            config_path = File.join(current, CONFIG_FILE)
            return config_path if File.exist?(config_path)
          end
          
          nil
        end
        
        def save_config(config)
          File.write(CONFIG_FILE, JSON.pretty_generate(config))
        end
        
        # Deep merge two hashes
        def deep_merge(hash1, hash2)
          hash1.merge(hash2) do |key, old_val, new_val|
            if old_val.is_a?(Hash) && new_val.is_a?(Hash)
              deep_merge(old_val, new_val)
            else
              new_val
            end
          end
        end
        
        def config_exists?
          File.exist?(CONFIG_FILE)
        end
        
        def get(key, default = nil)
          config = load_config
          keys = key.split('.')
          
          value = config
          keys.each do |k|
            value = value[k] if value.is_a?(Hash)
          end
          
          value || default
        end
        
        def set(key, value)
          config = load_config
          keys = key.split('.')
          
          current = config
          keys[0...-1].each do |k|
            current[k] ||= {}
            current = current[k]
          end
          
          current[keys.last] = value
          save_config(config)
        end
        
        def detect_mode
          # Check for Android project files
          gradle_files = Dir.glob('build.gradle*')
          settings_gradle = Dir.glob('settings.gradle*')
          
          if gradle_files.any? || settings_gradle.any?
            # Check if it's a Compose project
            build_file = gradle_files.first
            if build_file && File.exist?(build_file)
              content = File.read(build_file)
              if content.include?('compose') || content.include?('androidx.compose')
                return 'compose'
              end
            end
            
            # Default to XML for Android projects
            return 'xml'
          end
          
          # Default mode
          'all'
        end
        
        def project_type
          mode = get('mode', detect_mode)
          
          case mode
          when 'compose'
            'Jetpack Compose'
          when 'xml'
            'Android XML'
          when 'all'
            'Android (XML + Compose)'
          else
            'Unknown'
          end
        end
        
        def source_path
          get('source_directory', 'app/src/main')
        end
        
        def layouts_path
          Pathname.new(source_path).join(get('layouts_directory', 'assets/Layouts'))
        end
        
        def styles_path
          Pathname.new(source_path).join(get('styles_directory', 'assets/Styles'))
        end
        
        def view_path
          Pathname.new(source_path).join(get('view_directory', 'java/com/example/app/ui'))
        end
        
        def data_path
          Pathname.new(source_path).join(get('data_directory', 'java/com/example/app/data'))
        end
        
        def viewmodel_path
          Pathname.new(source_path).join(get('viewmodel_directory', 'java/com/example/app/viewmodel'))
        end
        
        def generated_path
          if get('mode') == 'compose'
            compose_config = get('compose', {})
            Pathname.new(source_path).join(compose_config['output_directory'] || 'java/com/example/app/generated')
          else
            Pathname.new(source_path).join(get('bindings_directory', 'java/com/example/app/bindings'))
          end
        end
      end
    end
  end
end